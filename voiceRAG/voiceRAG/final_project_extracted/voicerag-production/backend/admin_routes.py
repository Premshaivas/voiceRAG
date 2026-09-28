from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, func, select

from .auth import get_current_user
from .db import AuditEvent, Document, Transcript, User, UserRole

router = APIRouter(prefix="/api/admin", tags=["admin"])


async def require_admin(user: Annotated[User | None, Depends(get_current_user)]) -> User:
    if not user or user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Administrator access required")
    return user


async def audit(request: Request, actor: User, action: str, resource_type: str, resource_id: str | None = None, detail: dict | None = None) -> None:
    async with request.app.state.session_factory() as session:
        session.add(AuditEvent(actor_id=actor.id, action=action, resource_type=resource_type, resource_id=resource_id, detail=json.dumps(detail or {})))
        await session.commit()


@router.get("/users")
async def list_users(request: Request, admin: Annotated[User, Depends(require_admin)]):
    async with request.app.state.session_factory() as session:
        users = (await session.scalars(select(User).order_by(User.created_at.desc()))).all()
    return [{"id": user.id, "email": user.email, "role": user.role.value, "created_at": user.created_at} for user in users]


@router.patch("/users/{user_id}/role")
async def change_role(request: Request, user_id: str, role: str, admin: Annotated[User, Depends(require_admin)]):
    if role not in {item.value for item in UserRole}:
        raise HTTPException(status_code=422, detail="Invalid role")
    async with request.app.state.session_factory() as session:
        user = await session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.role = UserRole(role)
        await session.commit()
    await audit(request, admin, "user.role_changed", "user", user_id, {"role": role})
    return {"id": user_id, "role": role}


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(request: Request, document_id: str, admin: Annotated[User, Depends(require_admin)]):
    async with request.app.state.session_factory() as session:
        document = await session.get(Document, document_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        storage_path = document.storage_path
        await session.delete(document)
        await session.commit()
    try:
        request.app.state.pipeline.delete_document(document_id)
    except Exception:
        pass
    try:
        from pathlib import Path
        path = Path(storage_path)
        if path.is_file():
            path.unlink(missing_ok=True)
    except Exception:
        pass
    await audit(request, admin, "document.deleted", "document", document_id)


@router.get("/audit")
async def audit_log(request: Request, admin: Annotated[User, Depends(require_admin)], limit: int = 100):
    limit = max(1, min(limit, 500))
    async with request.app.state.session_factory() as session:
        events = (await session.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit))).all()
    return [{"id": item.id, "actor_id": item.actor_id, "action": item.action, "resource_type": item.resource_type, "resource_id": item.resource_id, "detail": item.detail, "created_at": item.created_at} for item in events]


@router.get("/usage")
async def usage(request: Request, admin: Annotated[User, Depends(require_admin)]):
    async with request.app.state.session_factory() as session:
        users = await session.scalar(select(func.count()).select_from(User))
        documents = await session.scalar(select(func.count()).select_from(Document))
        transcripts = await session.scalar(select(func.count()).select_from(Transcript))
    return {"users": users or 0, "documents": documents or 0, "transcripts": transcripts or 0, "generated_at": datetime.now(timezone.utc)}
