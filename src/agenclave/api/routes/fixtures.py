# Curated practice-bug ("fixture") routes. These let the web UI load a self-
# contained bug into the pipeline (Stage 1 triage -> Stage 2 code-fix) as a
# stand-in for connecting a real codebase. Read-only; no auth needed.

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ...fixtures import get_fixture, list_fixtures

router = APIRouter(prefix="/fixtures", tags=["fixtures"])


@router.get("")
def list_all() -> list[dict]:
    # Summary of every practice bug: enough to populate the UI picker.
    return [
        {"id": f.id, "title": f.title, "body": f.body, "category": f.category}
        for f in list_fixtures()
    ]


@router.get("/{fixture_id}")
def get_one(fixture_id: str) -> dict:
    # Full fixture, including the current (buggy) file so the demo can show it.
    f = get_fixture(fixture_id)
    if f is None:
        raise HTTPException(status_code=404, detail="fixture not found")
    return {
        "id": f.id,
        "title": f.title,
        "body": f.body,
        "category": f.category,
        "module": f.module,
        "code": f.buggy_code(),
    }
