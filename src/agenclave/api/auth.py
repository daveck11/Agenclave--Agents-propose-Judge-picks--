# Authentication: password hashing, JWT issue/verify, and current-user deps.
#
# Passwords are hashed with bcrypt directly (utf-8, 72-byte limit respected).
# Tokens are signed JWT (HS256) over `settings.secret_key`. Two dependencies:
# `get_current_user` (401s on a missing/invalid token) and `get_optional_user`
# (returns None instead, never raises) for routes that work anonymously.

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from .db import get_session
from .models import User

ALGORITHM = "HS256"
# bcrypt only considers the first 72 bytes; longer inputs raise on 4.x.
_BCRYPT_MAX_BYTES = 72


def _to_bcrypt_bytes(password: str) -> bytes:
    # Encode utf-8 and truncate to bcrypt's 72-byte limit (safe, deterministic).
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_to_bcrypt_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_to_bcrypt_bytes(password), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(sub: str, expires: timedelta | None = None) -> str:
    # Sign a JWT whose subject is the user id (as a string).
    if expires is None:
        expires = timedelta(minutes=settings.access_token_expire_minutes)
    now = datetime.now(timezone.utc)
    payload = {"sub": str(sub), "iat": now, "exp": now + expires}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    # Return the decoded claims, or None if the token is missing/invalid/expired.
    if not token:
        return None
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None


def _bearer_token(authorization: str | None) -> str | None:
    # Pull the raw token out of an `Authorization: Bearer <token>` header.
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


async def _user_from_token(token: str | None, session: AsyncSession) -> User | None:
    claims = decode_token(token or "")
    if not claims:
        return None
    sub = claims.get("sub")
    if sub is None:
        return None
    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        return None
    return await session.get(User, user_id)


async def get_current_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> User:
    # Require a valid bearer token; 401 on anything missing/invalid.
    user = await _user_from_token(_bearer_token(authorization), session)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_optional_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> User | None:
    # Best-effort: resolve a user if a valid token is present, else None.
    return await _user_from_token(_bearer_token(authorization), session)


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()
