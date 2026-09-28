from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import tempfile
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import get_current_user
from .db import Document, DocumentStatus, Transcript, User
from .storage import remove_file, save_upload, validate_extension

router = APIRouter(prefix="/api", tags=["voice-rag"])


class DocumentSummary(BaseModel):
    id: str
    title: str
    filename: str
    status: str
    transcript_id: str | None = None


class AnswerRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=6, ge=1, le=20)
    document_id: str | None = None


def _word_payload(transcript: Any) -> list[dict[str, Any]]:
    return [{"text": getattr(word, "text", None), "start": getattr(word, "start", None), "end": getattr(word, "end", None)} for word in (getattr(transcript, "words", None) or [])]


@router.get("/documents", response_model=list[DocumentSummary])
async def list_documents(request: Request, user: Annotated[User | None, Depends(get_current_user)]):
    async with request.app.state.session_factory() as session:
        statement = select(Document).order_by(Document.created_at.desc())
        if user:
            statement = statement.where(Document.owner_id == user.id)
        rows = (await session.scalars(statement)).all()
        return [DocumentSummary(id=d.id, title=d.title, filename=d.filename, status=d.status.value, transcript_id=d.transcript.id if d.transcript else None) for d in rows]


@router.get("/documents/{document_id}/audio")
async def document_audio(request: Request, document_id: str, user: Annotated[User | None, Depends(get_current_user)]):
    async with request.app.state.session_factory() as session:
        document = await session.get(Document, document_id)
    if not document or (user and document.owner_id != user.id) or (request.app.state.settings.auth_required and not user):
        raise HTTPException(status_code=404, detail="Document not found")
    local_path = Path(document.storage_path)
    if not local_path.is_file():
        try:
            url = await asyncio.to_thread(request.app.state.storage.presigned_get, document.storage_path, mimetypes.guess_type(document.filename)[0])
        except Exception as exc:
            raise HTTPException(status_code=404, detail="Audio object is unavailable") from exc
        return RedirectResponse(url, status_code=307)
    media_type = mimetypes.guess_type(document.filename)[0] or "application/octet-stream"
    file_size = local_path.stat().st_size
    range_header = request.headers.get("range")
    if not range_header:
        return FileResponse(local_path, media_type=media_type, filename=document.filename, headers={"Accept-Ranges": "bytes"})
    try:
        unit, value = range_header.split("=", 1)
        if unit != "bytes" or "," in value:
            raise ValueError
        start_text, end_text = value.split("-", 1)
        start = int(start_text) if start_text else max(0, file_size - int(end_text) - 1)
        end = int(end_text) if end_text else file_size - 1
        if start < 0 or start > end or end >= file_size:
            raise ValueError
    except ValueError as exc:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})

    length = end - start + 1

    def stream():
        with local_path.open("rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining:
                chunk = handle.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(stream(), status_code=206, media_type=media_type, headers={"Accept-Ranges": "bytes", "Content-Range": f"bytes {start}-{end}/{file_size}", "Content-Length": str(length), "Content-Disposition": f'inline; filename="{document.filename}"'})


@router.post("/documents/upload", response_model=DocumentSummary)
async def upload_document(request: Request, file: Annotated[UploadFile, File(...)], title: Annotated[str | None, Form()] = None, user: Annotated[User | None, Depends(get_current_user)] = None):
    filename = Path(file.filename or "audio").name
    try:
        suffix = validate_extension(filename)
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    document_title = (title or Path(filename).stem).strip()
    if not document_title:
        raise HTTPException(status_code=422, detail="Title cannot be empty")
    document_id = str(uuid.uuid4())
    destination = Path(request.app.state.settings.upload_dir) / f"{document_id}{suffix}"
    document = Document(id=document_id, owner_id=user.id if user else None, title=document_title, filename=filename, storage_path=str(destination), status=DocumentStatus.processing)
    async with request.app.state.session_factory() as session:
        session.add(document)
        await session.commit()
    try:
        await save_upload(file, destination)
        transcript = await asyncio.to_thread(request.app.state.transcriber.transcribe, str(destination))
        raw = getattr(transcript, "json_response", {}) or {}
        text = transcript.text
        metadata = {"document_id": document_id, "title": document_title, "assemblyai_transcript_id": transcript.id}
        if user:
            metadata["owner_id"] = user.id
        words = _word_payload(transcript)
        try:
            await asyncio.to_thread(request.app.state.pipeline.add_document, text, metadata, words)
        except TypeError as exc:
            if "positional" not in str(exc) and "argument" not in str(exc):
                raise
            await asyncio.to_thread(request.app.state.pipeline.add_document, text, metadata)
        async with request.app.state.session_factory() as session:
            saved = await session.get(Document, document_id)
            saved.status = DocumentStatus.completed
            session.add(Transcript(document_id=document_id, assemblyai_id=transcript.id, text=text, words_json=json.dumps(words), language_code=raw.get("language_code"), speech_model=raw.get("speech_model_used")))
            await session.commit()
            await session.refresh(saved)
            return DocumentSummary(id=saved.id, title=saved.title, filename=saved.filename, status=saved.status.value, transcript_id=transcript.id)
    except ValueError as exc:
        remove_file(destination)
        async with request.app.state.session_factory() as session:
            saved = await session.get(Document, document_id)
            saved.status, saved.error = DocumentStatus.failed, str(exc)
            await session.commit()
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except Exception as exc:
        remove_file(destination)
        async with request.app.state.session_factory() as session:
            saved = await session.get(Document, document_id)
            saved.status, saved.error = DocumentStatus.failed, str(exc)[:2000]
            await session.commit()
        raise HTTPException(status_code=502, detail=f"Audio processing failed: {exc}") from exc
    finally:
        await file.close()


@router.post("/answers")
async def answer_question(request: Request, body: AnswerRequest, user: Annotated[User | None, Depends(get_current_user)]):
    if request.app.state.settings.auth_required and not body.document_id:
        raise HTTPException(status_code=422, detail="document_id is required when authentication is enabled")
    if body.document_id and user:
        async with request.app.state.session_factory() as session:
            document = await session.get(Document, body.document_id)
        if not document or document.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Document not found")
    try:
        if user:
            return await asyncio.to_thread(request.app.state.answer_engine.answer, body.question, body.limit, body.document_id, user.id)
        return await asyncio.to_thread(request.app.state.answer_engine.answer, body.question, body.limit, body.document_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
