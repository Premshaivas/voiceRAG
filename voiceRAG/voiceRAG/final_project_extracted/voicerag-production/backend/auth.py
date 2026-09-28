from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Header, HTTPException, Request
from jose import JWTError, jwt

from .config import settings
from .db import User


def _password_bytes(password: str) -> bytes:
    """Prehash to avoid bcrypt's 72-byte input limit without truncating passwords."""
    return hashlib.sha256(password.encode("utf-8")).digest()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_password_bytes(password), password_hash.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        return False


def create_access_token(subject: str) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode({"sub": subject, "exp": expires}, settings.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        subject = payload.get("sub")
        return str(subject) if subject else None
    except JWTError:
        return None


async def get_current_user(request: Request, authorization: str | None = Header(default=None)) -> User | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        if request.app.state.settings.auth_required:
            raise HTTPException(status_code=401, detail="Bearer access token required")
        return None
    user_id = decode_access_token(authorization.split(" ", 1)[1].strip())
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")
    async with request.app.state.session_factory() as session:
        user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return user
