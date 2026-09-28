from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from .auth import create_access_token, hash_password, verify_password
from .db import User, UserRole
from .session_model import RefreshSession
from .session_tokens import new_csrf_token, new_token, token_hash

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=200)


def _cookie_kwargs(request: Request) -> dict:
    return {"httponly": True, "secure": request.app.state.settings.app_env != "development", "samesite": "lax", "path": "/"}


async def _issue_session(request: Request, response: Response, user_id: str, family_id: str | None = None):
    refresh, csrf = new_token(), new_csrf_token()
    session = RefreshSession(user_id=user_id, family_id=family_id or str(uuid.uuid4()), token_hash=token_hash(refresh), csrf_hash=token_hash(csrf), expires_at=datetime.now(timezone.utc) + timedelta(days=request.app.state.settings.refresh_days))
    async with request.app.state.session_factory() as db:
        db.add(session)
        await db.commit()
    response.set_cookie(request.app.state.settings.refresh_cookie_name, refresh, **_cookie_kwargs(request), max_age=request.app.state.settings.refresh_days * 86400)
    return {"access_token": create_access_token(user_id), "csrf_token": csrf}


@router.post("/register")
async def register(request: Request, body: Credentials, response: Response):
    async with request.app.state.session_factory() as db:
        if await db.scalar(select(User).where(User.email == body.email.lower())):
            raise HTTPException(status_code=409, detail="Email is already registered")
        email = body.email.lower()
        role = UserRole.admin if request.app.state.settings.admin_email and email == request.app.state.settings.admin_email.lower() else UserRole.user
        user = User(email=email, password_hash=hash_password(body.password), role=role)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return await _issue_session(request, response, user.id)


@router.post("/login")
async def login(request: Request, body: Credentials, response: Response):
    async with request.app.state.session_factory() as db:
        user = await db.scalar(select(User).where(User.email == body.email.lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return await _issue_session(request, response, user.id)


@router.post("/refresh")
async def refresh(request: Request, response: Response, x_csrf_token: str | None = Header(default=None)):
    raw = request.cookies.get(request.app.state.settings.refresh_cookie_name)
    if not raw or not x_csrf_token:
        raise HTTPException(status_code=401, detail="Refresh cookie and CSRF token are required")
    async with request.app.state.session_factory() as db:
        session = await db.scalar(select(RefreshSession).where(RefreshSession.token_hash == token_hash(raw)))
        if not session:
            raise HTTPException(status_code=401, detail="Invalid refresh session")
        if session.used or session.revoked:
            await db.execute(RefreshSession.__table__.update().where(RefreshSession.family_id == session.family_id).values(revoked=True))
            await db.commit()
            raise HTTPException(status_code=401, detail="Refresh-token reuse detected")
        if session.expires_at < datetime.now(timezone.utc) or session.csrf_hash != token_hash(x_csrf_token):
            raise HTTPException(status_code=401, detail="Invalid refresh session")
        session.used = True
        await db.commit()
        user_id, family_id = session.user_id, session.family_id
    return await _issue_session(request, response, user_id, family_id)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, x_csrf_token: str | None = Header(default=None)):
    raw = request.cookies.get(request.app.state.settings.refresh_cookie_name)
    if raw and x_csrf_token:
        async with request.app.state.session_factory() as db:
            session = await db.scalar(select(RefreshSession).where(RefreshSession.token_hash == token_hash(raw)))
            if session and session.csrf_hash == token_hash(x_csrf_token):
                session.revoked = True
                await db.commit()
    response.delete_cookie(request.app.state.settings.refresh_cookie_name, path="/")
