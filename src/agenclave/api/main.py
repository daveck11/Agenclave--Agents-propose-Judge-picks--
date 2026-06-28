# FastAPI app factory for the Agenclave service.
#
# Stage 1 (triage) + Stage 2 (best-of-N pipeline) + Stage 3 (accounts,
# persistence, recommendations). Routes live in `agenclave.api.routes.*`; this
# module just assembles them, configures CORS, and initialises the database on
# startup. `app = create_app()` is kept at module level so the usual
# `uvicorn agenclave.api.main:app` entry point still works.

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import init_db
from .routes import auth, issues, runs, triage

logger = logging.getLogger("agenclave.api")

# The Vite dev server (the demo frontend) calls the API from these origins.
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create the database schema before serving requests.
    await init_db()
    yield


def create_app() -> FastAPI:
    # Build and configure the FastAPI application.
    app = FastAPI(title="Agenclave API", version="0.2.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(triage.router)
    app.include_router(auth.router)
    app.include_router(issues.router)
    app.include_router(runs.router)
    return app


app = create_app()
