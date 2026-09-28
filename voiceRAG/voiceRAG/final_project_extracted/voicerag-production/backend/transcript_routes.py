from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from .auth import get_current_user
from .db import Document, Transcript, User

router = APIRouter(prefix="/api", tags=["transcripts"])


async def owned_document(request: Request, document_id: str, user: User | None) -> Document:
    async with request.app.state.session_factory() as session:
        document = await session.get(Document, document_id)
    if not document or (user and document.owner_id != user.id) or (request.app.state.settings.auth_required and not user):
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.get("/documents/{document_id}/transcript")
async def get_transcript(request: Request, document_id: str, user: Annotated[User | None, Depends(get_current_user)]):
    document = await owned_document(request, document_id, user)
    async with request.app.state.session_factory() as session:
        transcript = await session.scalar(select(Transcript).where(Transcript.document_id == document.id))
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")
    return {"document_id": document.id, "title": document.title, "language_code": transcript.language_code, "speech_model": transcript.speech_model, "text": transcript.text, "words": json.loads(transcript.words_json or "[]")}


@router.get("/documents/{document_id}/transcript/search")
async def search_transcript(request: Request, document_id: str, q: str, user: Annotated[User | None, Depends(get_current_user)]):
    if not q.strip():
        raise HTTPException(status_code=422, detail="Search query is required")
    document = await owned_document(request, document_id, user)
    async with request.app.state.session_factory() as session:
        transcript = await session.scalar(select(Transcript).where(Transcript.document_id == document.id))
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")
    text = transcript.text
    needle = q.strip().lower()
    matches = []
    start = 0
    while len(matches) < 50:
        index = text.lower().find(needle, start)
        if index < 0:
            break
        matches.append({"start": index, "end": index + len(q.strip()), "excerpt": text[max(0, index - 100):min(len(text), index + len(q.strip()) + 100)]})
        start = index + max(1, len(needle))
    return {"document_id": document.id, "query": q, "matches": matches}
