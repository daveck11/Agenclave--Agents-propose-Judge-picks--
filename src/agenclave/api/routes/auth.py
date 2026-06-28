# Auth routes: register, login, and the current-user lookup.
#
# Tokens are JWTs (see `..auth`); passwords are bcrypt-hashed. Duplicate emails
# are rejected with 409 and bad credentials with 401.

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import (
    create_access_token,
    get_current_user,
    get_user_by_email,
    hash_password,
    verify_password,
)
from ..db import get_session
from ..models import User
from ..schemas import LoginRequest, RegisterRequest, Token, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_token(user: User) -> Token:
    token = create_access_token(sub=user.id)
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(
    req: RegisterRequest, session: AsyncSession = Depends(get_session)
) -> Token:
    # Create an account; 409 if the email is already taken.
    existing = await get_user_by_email(session, req.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an account with this email already exists",
        )
    user = User(email=req.email, hashed_password=hash_password(req.password))
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return _issue_token(user)


@router.post("/login", response_model=Token)
async def login(
    req: LoginRequest, session: AsyncSession = Depends(get_session)
) -> Token:
    # Exchange credentials for a token; 401 on any mismatch.
    user = await get_user_by_email(session, req.email)
    if user is None or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="incorrect email or password",
        )
    return _issue_token(user)


@router.get("/me", response_model=UserOut)
async def me(current: User = Depends(get_current_user)) -> UserOut:
    # Return the authenticated account.
    return UserOut.model_validate(current)
