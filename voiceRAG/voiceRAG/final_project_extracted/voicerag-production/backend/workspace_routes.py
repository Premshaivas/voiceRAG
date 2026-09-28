from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from .auth import get_current_user
from .db import User, VoiceConversation, VoiceMessage, Workspace, WorkspaceMember

router = APIRouter(prefix="/api", tags=["workspace"])


async def required_user(user: Annotated[User | None, Depends(get_current_user)]) -> User:
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


class WorkspaceInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class VoiceInput(BaseModel):
    role: str = Field(pattern="^(user|agent|system)$")
    text: str = Field(min_length=1, max_length=20_000)


@router.post("/workspaces")
async def create_workspace(request: Request, body: WorkspaceInput, user: Annotated[User, Depends(required_user)]):
    async with request.app.state.session_factory() as session:
        workspace = Workspace(name=body.name, created_by=user.id)
        session.add(workspace)
        await session.flush()
        session.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"))
        await session.commit()
    return {"id": workspace.id, "name": workspace.name, "role": "owner"}


@router.get("/workspaces")
async def list_workspaces(request: Request, user: Annotated[User, Depends(required_user)]):
    async with request.app.state.session_factory() as session:
        rows = (await session.execute(select(Workspace, WorkspaceMember.role).join(WorkspaceMember, Workspace.id == WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id))).all()
    return [{"id": workspace.id, "name": workspace.name, "role": role} for workspace, role in rows]


@router.post("/voice-conversations")
async def create_voice_conversation(request: Request, user: Annotated[User, Depends(required_user)]):
    async with request.app.state.session_factory() as session:
        conversation = VoiceConversation(owner_id=user.id)
        session.add(conversation)
        await session.commit()
    return {"id": conversation.id, "title": conversation.title}


@router.get("/voice-conversations")
async def list_voice_conversations(request: Request, user: Annotated[User, Depends(required_user)]):
    async with request.app.state.session_factory() as session:
        rows = (await session.scalars(select(VoiceConversation).where(VoiceConversation.owner_id == user.id).order_by(VoiceConversation.created_at.desc()))).all()
    return [{"id": item.id, "title": item.title, "created_at": item.created_at} for item in rows]


@router.get("/voice-conversations/{conversation_id}")
async def get_voice_conversation(request: Request, conversation_id: str, user: Annotated[User, Depends(required_user)]):
    async with request.app.state.session_factory() as session:
        conversation = await session.scalar(select(VoiceConversation).where(VoiceConversation.id == conversation_id, VoiceConversation.owner_id == user.id))
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        messages = (await session.scalars(select(VoiceMessage).where(VoiceMessage.conversation_id == conversation.id).order_by(VoiceMessage.created_at))).all()
    return {"id": conversation.id, "title": conversation.title, "messages": [{"role": item.role, "text": item.text, "created_at": item.created_at} for item in messages]}


@router.post("/voice-conversations/{conversation_id}/messages")
async def add_voice_message(request: Request, conversation_id: str, body: VoiceInput, user: Annotated[User, Depends(required_user)]):
    async with request.app.state.session_factory() as session:
        conversation = await session.scalar(select(VoiceConversation).where(VoiceConversation.id == conversation_id, VoiceConversation.owner_id == user.id))
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        message = VoiceMessage(conversation_id=conversation.id, role=body.role, text=body.text)
        session.add(message)
        await session.commit()
    return {"id": message.id, "role": message.role, "text": message.text}
