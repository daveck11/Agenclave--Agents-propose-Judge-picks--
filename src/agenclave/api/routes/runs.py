# Stage 2 pipeline routes.
#
# `POST /runs` is the full pipeline: Stage 1 triage as the *gate* for Stage 2.
# It works anonymously exactly as before (dry run by default, live dispatch when
# `live` is set). When the caller is authenticated, the run is ALSO persisted and
# its id returned. `GET /runs` / `GET /runs/{id}` list a user's own runs;
# `GET /runs/latest` stays an anonymous demo endpoint over chairman_eval.json.

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...classifier.predict import ModelsNotTrained, predict_triage
from ...config import RESULTS_DIR, settings
from ...harness import Chairman, Task, build_agents, dispatch
from ..auth import get_current_user, get_optional_user
from ..db import get_session
from ..models import Run, User
from ..schemas import RunOut, RunRequest

logger = logging.getLogger("agenclave.api")

router = APIRouter(tags=["runs"])

# Rough $/1M tokens (input, output) — same table as scripts/run_chairman.py, so
# the web cost projection matches the CLI.
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
    # The full pipeline, end to end, with Stage 1 as the *gate* for Stage 2:
    #
    #   1. Triage the issue (Stage 1 front door).
    #   2. Gate: only a `bug` proceeds; non-bugs are filtered out at $0 cost.
    #   3. If it passed the gate AND `live` is set, dispatch to N agents and let
    #      the Chairman judge (Stage 2). Otherwise it's a dry run (no API calls).
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
    projection = sum(_cost_per_call(m) for m in models) + _cost_per_call(
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
        "config": {
            "provider": settings.provider,
            "agent_models": models,
            "chairman_model": settings.chairman_model,
        },
        "cost": {
            "projection_usd": round(projection, 4),
            "calls": len(models) + 1,
            "spent_usd": 0.0,
        },
        "ran_live": False,
        "candidates": [],
        "decision": None,
        "selected_patch": "",
    }

    # Gate closed (non-bug) or a dry run → stop before any live dispatch.
    if passed and req.live:
        # Stage 2 live dispatch.
        statement = f"{req.title}\n\n{req.body}".strip()
        task = Task(
            instance_id="web-run",
            repo="(web demo — issue text only, no repo checkout)",
            problem_statement=statement,
            triage_label=label,
            triage_severity=tri.get("severity"),
        )
        try:
            agents = build_agents(settings.provider, models)
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
                "resolve_rate_note": (
                    "Patches come from the issue text only, without a repo checkout. "
                    "The CLI runner targets real SWE-bench instances for benchmarked "
                    "results."
                ),
            }
        )
        out["cost"]["spent_usd"] = round(projection, 4)

    # Persist the run for an authenticated caller (anonymous behaviour unchanged).
    if user is not None:
        run = Run(
            user_id=user.id,
            issue_id=req.issue_id,
            title=req.title,
            body=req.body,
            gate_passed=passed,
            ran_live=out["ran_live"],
            result=out,
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        out["run_id"] = run.id

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


@router.get("/runs/latest")
def latest_run() -> dict:
    # Serve the most recent Stage 2 Chairman run (results/chairman_eval.json) so
    # the demo can render real candidate patches + the judge's decision. Returns
    # 404 (with guidance) when no live run has been recorded yet.
    path = RESULTS_DIR / "chairman_eval.json"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="no Stage 2 run found; run `python scripts/run_chairman.py --live`",
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.exception("failed to read chairman_eval.json")
        raise HTTPException(status_code=500, detail="could not read run results") from exc


@router.get("/resolve-rate")
def resolve_rate() -> dict:
    # Serve the SWE-bench resolve rate measured offline by scripts/grade_swebench.py
    # (the official harness, in Docker, on the author's machine). The app only
    # *displays* this committed number — opening the link never runs Docker. Returns
    # 404 until a real grading has been recorded, so the UI never shows a fake score.
    path = RESULTS_DIR / "resolve_rate.json"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="no resolve rate recorded yet; run scripts/grade_swebench.py with Docker",
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.exception("failed to read resolve_rate.json")
        raise HTTPException(status_code=500, detail="could not read resolve rate") from exc


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
