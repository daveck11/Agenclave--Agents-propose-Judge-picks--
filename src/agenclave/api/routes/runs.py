# Pipeline + run persistence routes.
#
# `POST /runs` is the full pipeline: triage as the gate, then trust-scored routing
# and (when `live` is set) best-of-N dispatch + the Chairman judge. It works
# anonymously (dry run by default) and never auto-saves. Authenticated users keep a
# run with `POST /runs/save`; `GET /runs` / `GET /runs/{id}` / `DELETE /runs/{id}`
# manage a user's own saved runs.

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...classifier.predict import ModelsNotTrained, predict_triage
from ...config import settings
from ...fixtures import get_fixture
from ...harness import Chairman, Task, build_agents, dispatch, route
from ...harness.reliability import record_outcome
from ...harness.trust import trust_rank
from ...harness.verify import verify_patch
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
    # Optional practice-bug fixture: when set, the agents are shown its file and
    # each candidate is verified against its own tests (the real trust loop).
    fixture = get_fixture(req.fixture_id) if req.fixture_id else None

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
            instance_id=fixture.id if fixture else "web-run",
            repo=(
                str(fixture.repo)
                if fixture
                else "(web demo - issue text only, no repo checkout)"
            ),
            problem_statement=statement,
            triage_label=label,
            triage_severity=tri.get("severity"),
            files={fixture.module: fixture.buggy_code()} if fixture else {},
        )
        try:
            agents = build_agents(settings.provider, run_models)
            chairman = Chairman(settings.chairman_model)
            candidates = await dispatch(task, agents)
        except Exception as exc:  # noqa: BLE001 - surface a safe message, log detail.
            logger.exception("live dispatch failed")
            raise HTTPException(
                status_code=502,
                detail=f"provider call failed: {type(exc).__name__}. Check API keys in .env.",
            ) from exc

        # A fixture ships real tests, so verify BEFORE the Chairman speaks: apply
        # each candidate in a sandbox, run the tests, and rank by what passes.
        # verify_patch is blocking (subprocess), so run the candidates concurrently
        # off the event loop with a tight timeout. Verification must NEVER fail the
        # run - any error degrades to a judge-only result.
        vrs: dict = {}
        winner = None
        if fixture is not None:
            out["fixture"] = {"id": fixture.id, "module": fixture.module}
            try:

                async def _verify(cand):
                    vr = await asyncio.to_thread(
                        verify_patch, cand.patch, fixture.repo, fixture.test_cmd,
                        timeout=60,
                    )
                    return cand.agent_name, vr

                results = await asyncio.gather(
                    *(_verify(c) for c in candidates if c.ok)
                )
                vrs = dict(results)
                # In-loop verification: record each outcome so the router builds a
                # genuine track record as the app is used (the no-leakage rule only
                # bars a held-out grade, which this is not; the non-fixture web path
                # records nothing because it has no verification).
                for name, vr in vrs.items():
                    record_outcome(name, label, vr.tests_passed)
                ranking = trust_rank(candidates, vrs, category=label)
                winner = ranking[0].agent_name if ranking else None
                out["verification"] = [
                    {
                        "agent": v.agent_name,
                        "tier": v.tier,
                        "reason": v.reason,
                        "applies": bool(v.agent_name in vrs and vrs[v.agent_name].applies),
                        "tests_passed": bool(
                            v.agent_name in vrs and vrs[v.agent_name].tests_passed
                        ),
                        "passed": vrs[v.agent_name].passed if v.agent_name in vrs else 0,
                        "total": vrs[v.agent_name].total if v.agent_name in vrs else 0,
                    }
                    for v in ranking
                ]
                out["verified_winner"] = winner
            except Exception:  # noqa: BLE001 - never 500 the run over verification
                logger.exception("fixture verification failed for %s", fixture.id)
                out["verification_error"] = (
                    "verification could not run for this task (see server logs)"
                )

        # The Chairman: for a verified fixture run, EXPLAIN the winner in its own
        # words (comparing the candidates' approaches, using the test results);
        # otherwise judge the patches by reading.
        try:
            if fixture is not None and winner is not None:
                decision = await chairman.explain(task, candidates, vrs, winner)
            else:
                decision = await chairman.judge(task, candidates)
        except Exception as exc:  # noqa: BLE001
            logger.exception("chairman call failed")
            raise HTTPException(
                status_code=502,
                detail=f"judge call failed: {type(exc).__name__}. Check API keys in .env.",
            ) from exc

        # The final patch is the verified winner's for a fixture; the judge's pick
        # otherwise.
        final_agent = (
            winner if (fixture is not None and winner is not None)
            else decision.selected_agent
        )
        selected_patch = next(
            (c.patch for c in candidates if c.agent_name == final_agent), ""
        ) or (decision.synthesized_patch or "")
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
