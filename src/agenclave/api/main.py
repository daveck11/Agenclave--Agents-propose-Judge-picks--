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
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..config import ROOT
from .db import init_db
from .routes import auth, issues, runs, triage

logger = logging.getLogger("agenclave.api")

# Built single-page app (produced by `npm run build` in frontend/). When present,
# the API serves it at "/" so the whole product is one origin / one process.
FRONTEND_DIST = ROOT / "frontend" / "dist"

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

    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    # Serve the built React app (if present) for a single-origin, single-command
    # deployment. API routes are registered first, so they win; the catch-all
    # only handles unmatched GETs — real static files, else index.html (so
    # client-side deep links like /workspace resolve to the SPA).
    index = FRONTEND_DIST / "index.html"
    if not index.is_file():
        logger.info("frontend build not found at %s; serving API only", FRONTEND_DIST)
        return

    assets = FRONTEND_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)


app = create_app()
