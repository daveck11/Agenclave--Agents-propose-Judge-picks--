# Shared test fixtures: src on sys.path + an in-memory SQLite app client.
#
# Each test that needs persistence gets a fresh in-memory aiosqlite database
# (StaticPool so the single in-memory connection is shared across requests). We
# point the db module's engine/sessionmaker at it before the app's lifespan runs
# `init_db`, so table creation and every request share one event loop + one
# connection. Uses FastAPI's sync `TestClient`, which drives the async routes.

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agenclave.api import db  # noqa: E402
from agenclave.api.main import app  # noqa: E402


@pytest.fixture
def client():
    # A TestClient backed by a fresh in-memory database.
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # Point the live module globals at the in-memory engine. `get_session` and
    # `init_db` read these at call time, so the lifespan creates the schema on
    # this engine inside the TestClient event loop (no cross-loop aiosqlite use).
    orig_engine, orig_factory = db.engine, db.async_session_factory
    db.engine = engine
    db.async_session_factory = session_factory

    try:
        with TestClient(app) as c:  # enters lifespan -> init_db() -> create_all
            yield c
    finally:
        db.engine, db.async_session_factory = orig_engine, orig_factory
