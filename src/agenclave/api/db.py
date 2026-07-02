# Async SQLAlchemy 2.0 wiring for accounts + persistence.
#
# One async engine + sessionmaker for the app, a declarative `Base`, the
# `get_session` FastAPI dependency (yields an `AsyncSession`), and `init_db`
# (create_all on startup). The default URL is a local aiosqlite file under
# `data/`; tests override `get_session` with an in-memory engine.

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from ..config import DATA_DIR, settings


class Base(DeclarativeBase):
    # Declarative base shared by every ORM model.
    pass


# The default sqlite file lives under data/; make sure the directory exists so
# engine creation never trips over a missing path (tolerant of it pre-existing).
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Neon / managed Postgres require SSL; asyncpg takes it via connect_args (not a URL
# query param). SQLite ignores it.
_connect_args = (
    {"ssl": True} if settings.database_url.startswith("postgresql+asyncpg://") else {}
)
engine = create_async_engine(
    settings.database_url, future=True, connect_args=_connect_args
)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    # FastAPI dependency: yield a session scoped to one request.
    async with async_session_factory() as session:
        yield session


async def init_db() -> None:
    # Create all tables (idempotent). Import models for side-effect registration.
    from . import models  # noqa: F401 - ensures tables are registered on Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
