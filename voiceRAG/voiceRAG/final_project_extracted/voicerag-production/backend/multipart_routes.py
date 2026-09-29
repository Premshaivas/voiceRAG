from __future__ import annotations

import json
import math
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from .auth import get_current_user
from .db import Document, DocumentStatus, Job, JobStatus, OutboxEvent, User
from .multipart_model import MultipartStatus, MultipartUpload

router = APIRouter(prefix="/api/uploads", tags=["uploads"])
PART_SIZE_BYTES = 16 * 1024 * 1024


class InitiateRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=500)
    content_type: str = Field(default="application/octet-stream", max_length=255)
    size_bytes: int = Field(gt=0)
    title: str | None = Field(default=None, max_length=500)


class CompleteRequest(BaseModel):
    parts: list[dict[str, str | int]] = Field(min_length=1)


def _owned(row: MultipartUpload | None, user: User | None, auth_required: bool) -> bool:
    if not row or row.status != MultipartStatus.pending:
        return False
    return not user and not auth_required or bool(user and row.owner_id == user.id)


@router.post("/initiate")
async def initiate(request: Request, body: InitiateRequest, user: Annotated[User | None, Depends(get_current_user)]):
    if body.size_bytes > request.app.state.settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds configured upload limit")
    object_key = f"incoming/{uuid.uuid4()}-{body.filename.replace('/', '_')}"
    upload_id = request.app.state.storage.create_multipart(object_key, body.content_type)
    count = math.ceil(body.size_bytes / PART_SIZE_BYTES)
    row = MultipartUpload(owner_id=user.id if user else None, object_key=object_key, storage_upload_id=upload_id, filename=body.filename, content_type=body.content_type, size_bytes=body.size_bytes, part_size_bytes=PART_SIZE_BYTES, part_count=count)
    async with request.app.state.session_factory() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return {"upload_id": row.id, "storage_upload_id": upload_id, "part_size_bytes": PART_SIZE_BYTES, "part_count": count}


@router.get("/{upload_id}/parts")
async def presign_parts(request: Request, upload_id: str, start: int = 1, count: int = 10, user: Annotated[User | None, Depends(get_current_user)] = None):
    if start < 1 or count < 1 or count > 100:
        raise HTTPException(status_code=422, detail="Invalid part range")
    async with request.app.state.session_factory() as session:
        row = await session.get(MultipartUpload, upload_id)
    if not _owned(row, user, request.app.state.settings.auth_required):
        raise HTTPException(status_code=404, detail="Multipart upload not found")
    end = min(start + count - 1, row.part_count)
    if start > row.part_count:
        raise HTTPException(status_code=422, detail="Part range starts beyond upload")
    return {"parts": [{"part_number": number, "url": request.app.state.storage.presigned_part(row.object_key, row.storage_upload_id, number)} for number in range(start, end + 1)]}


@router.post("/{upload_id}/complete")
async def complete(request: Request, upload_id: str, body: CompleteRequest, user: Annotated[User | None, Depends(get_current_user)]):
    async with request.app.state.session_factory() as session:
        row = await session.get(MultipartUpload, upload_id)
        if not _owned(row, user, request.app.state.settings.auth_required):
            raise HTTPException(status_code=404, detail="Multipart upload not found")
        if len(body.parts) != row.part_count:
            raise HTTPException(status_code=422, detail=f"Expected {row.part_count} parts")
        parts = [{"PartNumber": int(item["part_number"]), "ETag": str(item["etag"])} for item in body.parts]
        if sorted(p["PartNumber"] for p in parts) != list(range(1, row.part_count + 1)):
            raise HTTPException(status_code=422, detail="Parts must contain every part number exactly once")
        request.app.state.storage.complete_multipart(row.object_key, row.storage_upload_id, parts)
        document = Document(owner_id=user.id if user else None, title=row.filename.rsplit('.', 1)[0], filename=row.filename, storage_path=row.object_key, status=DocumentStatus.pending)
        session.add(document)
        await session.flush()
        job = Job(document_id=document.id, kind="process_upload", status=JobStatus.pending)
        session.add(job)
        session.add(OutboxEvent(event_type="document.processing_requested", aggregate_id=document.id, payload=json.dumps({"document_id": document.id, "object_key": row.object_key}), status="pending"))
        row.status = MultipartStatus.completed
        await session.commit()
    return {"document_id": document.id, "status": "queued"}
