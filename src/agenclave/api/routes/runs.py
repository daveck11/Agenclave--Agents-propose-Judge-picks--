# Pipeline + run persistence routes.
#
# `POST /runs` is the full pipeline: triage as the gate, then trust-scored routing
# and (when `live` is set) best-of-N dispatch + the Chairman judge. It works
# anonymously (dry run by default) and never auto-saves. Authenticated users keep a
# run with `POST /runs/save`; `GET /runs` / `GET /runs/{id}` / `DELETE /runs/{id}`
# manage a user's own saved runs.

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...classifier.predict import ModelsNotTrained, predict_triage
from ...config import settings
from ...harness import Chairman, Task, build_agents, dispatch, route
from ..auth import get_current_user, get_optional_user
from ..db import get_session
from ..models import Run, User
from ..schemas import RunOut, RunRequest, RunSaveRequest

logger = logging.getLogger("agenclave.api")

router = APIRouter(tags=["runs"])

# Rough $/1M tokens (input, output) for the live cost projection shown in the UI.
_PRICE_PER_M = {
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.5, 10.0),
    # BlackBox-routed model ids (same per-1M rates as the underlying models).
    "blackboxai/anthropic/claude-opus-4.7": (5.0, 25.0),
    "blackboxai/anthropic/claude-sonnet-4.6": (3.0, 15.0),
    "blackboxai/openai/gpt-5.4": (2.5, 15.0),
    "blackboxai/google/gemini-3.1-flash-lite": (0.25, 1.5),
    "blackboxai/deepseek/deepseek-v4-pro": (0.43, 0.87),
}
_EST_INPUT_TOKENS = 2500
_EST_OUTPUT_TOKENS = 1200


def _cost_per_call(model: str) -> float:
    pin, pout = _PRICE_PER_M.get(model, (0.0, 0.0))
    return (_EST_INPUT_TOKENS * pin + _EST_OUTPUT_TOKENS * pout) / 1_000_000


@router.post("/runs")
async def run_pipeline(
    req: RunRequest,
    user: User | None = Depends(get_optional_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    # Full pipeline: triage the issue, gate on the label (only a bug goes
    # further), then if `live` is set dispatch to the routed agents and let
    # the Chairman judge. Without `live` it stops before any API call.
    try:
        tri = predict_triage(req.title, req.body)
    except ModelsNotTrained as exc:
        raise HTTPException(
            status_code=503,
            detail="models not trained; run scripts/train_classifier.py",
        ) from exc

    label = tri["label"]
    passed = label == "bug"
    models = settings.agent_model_list

    # When the gate passes, route to a subset of the panel instead of always
    # dispatching everyone. Read-only: a web run has no repo checkout, so
    # there is no verify_patch result here, and we must not call
    # record_outcome without one (writing the judge's opinion into the
    # reliability store would defeat the point of it).
    routing = route(label, models, settings.route_k) if passed else None
    run_models = routing.selected if routing else models

    projection = sum(_cost_per_call(m) for m in run_models) + _cost_per_call(
        settings.chairman_model
    )

    out: dict = {
        "triage": {
            "label": label,
            "confidence": tri["label_confidence"],
            "top_tokens": tri["top_tokens"],
        },
        "gate": {
            "passed": passed,
            "reason": (
                "Bug. Sent to the agents."
                if passed
                else f"Not a bug ({label}). Harness skipped."
            ),
        },
        "routing": (
            {
                "selected": routing.selected,
                "considered": routing.considered,
                "reason": routing.reason,
                "k": settings.route_k,
            }
            if routing
            else None
        ),
        "config": {
            "provider": settings.provider,
            "agent_models": models,
            "chairman_model": settings.chairman_model,
        },
        "cost": {
            "projection_usd": round(projection, 4),
            "calls": len(run_models) + 1,
            "spent_usd": 0.0,
        },
        "ran_live": False,
        "candidates": [],
        "decision": None,
        "selected_patch": "",
    }

    if passed and req.live:
        statement = f"{req.title}\n\n{req.body}".strip()
        task = Task(
            instance_id="web-run",
            repo="(web demo - issue text only, no repo checkout)",
            problem_statement=statement,
            triage_label=label,
            triage_severity=tri.get("severity"),
        )
        try:
            agents = build_agents(settings.provider, run_models)
            chairman = Chairman(settings.chairman_model)
            candidates = await dispatch(task, agents)
            decision = await chairman.judge(task, candidates)
        except Exception as exc:  # noqa: BLE001 - surface a safe message, log detail.
            logger.exception("live pipeline run failed")
            raise HTTPException(
                status_code=502,
                detail=f"provider call failed: {type(exc).__name__}. Check API keys in .env.",
            ) from exc

        selected_patch = decision.synthesized_patch or next(
            (c.patch for c in candidates if c.agent_name == decision.selected_agent), ""
        )
        out.update(
            {
                "ran_live": True,
                "candidates": [
                    {"agent": c.agent_name, "ok": c.ok, "error": c.error, "patch": c.patch}
                    for c in candidates
                ],
                "decision": {
                    "selected_agent": decision.selected_agent,
                    "ranking": decision.ranking,
                    "rationale": decision.rationale,
                    "synthesized": bool(decision.synthesized_patch),
                },
                "selected_patch": selected_patch,
            }
        )
        out["cost"]["spent_usd"] = round(projection, 4)

    # runs are never auto-saved; the user keeps one via POST /runs/save
    return out


@router.get("/runs", response_model=list[RunOut])
async def list_runs(
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Run]:
    # List the caller's persisted runs, newest first.
    result = await session.execute(
        select(Run).where(Run.user_id == current.id).order_by(Run.id.desc())
    )
    return list(result.scalars().all())


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run(
    run_id: int,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Run:
    # Fetch one of the caller's runs (404 if not owned).
    run = await session.get(Run, run_id)
    if run is None or run.user_id != current.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    return run


@router.post("/runs/save")
async def save_run(
    req: RunSaveRequest,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    # Persist a run the user chose to keep (runs are not auto-saved).
    result = req.result or {}
    run = Run(
        user_id=current.id,
        issue_id=req.issue_id,
        title=req.title,
        body=req.body,
        gate_passed=bool((result.get("gate") or {}).get("passed")),
        ran_live=bool(result.get("ran_live")),
        result=result,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return {"run_id": run.id}


@router.delete(
    "/runs/{run_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_run(
    run_id: int,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    # Delete one of the caller's runs (404 if not owned).
    run = await session.get(Run, run_id)
    if run is None or run.user_id != current.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    await session.delete(run)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
