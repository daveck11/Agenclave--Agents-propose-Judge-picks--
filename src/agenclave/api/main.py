# Stage 1 FastAPI triage service.
#
# Wraps the torch-free `predict_triage` inference path behind a small HTTP API:
#
# - `GET  /health`  -> liveness + whether the production model is loadable.
# - `POST /triage`  -> classify an issue into type (and severity if that optional
#   head is present; the shipped deliverable is type-only, so severity is null).
#
# Run with::
#
#     uvicorn agenclave.api.main:app --reload

from __future__ import annotations

import json
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from agenclave.classifier.predict import ModelsNotTrained, predict_triage
from agenclave.config import RESULTS_DIR, settings
from agenclave.harness import Chairman, Task, build_agents, dispatch

from .schemas import RunRequest, TriageRequest, TriageResponse

# Rough $/1M tokens (input, output) — same table as scripts/run_chairman.py, so
# the web cost projection matches the CLI.
_PRICE_PER_M = {
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.5, 10.0),
}
_EST_INPUT_TOKENS = 2500
_EST_OUTPUT_TOKENS = 1200


def _cost_per_call(model: str) -> float:
    pin, pout = _PRICE_PER_M.get(model, (0.0, 0.0))
    return (_EST_INPUT_TOKENS * pin + _EST_OUTPUT_TOKENS * pout) / 1_000_000

logger = logging.getLogger("agenclave.api")

app = FastAPI(title="Agenclave Triage API", version="0.1.0")

# Permissive CORS for local dev: the Vite demo calls this from another port.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    # Liveness probe that also reports whether the models can be loaded.
    models_loaded = True
    try:
        # A blank-ish probe is enough to force model load via predict_triage;
        # title carries signal so the request schema is satisfied.
        predict_triage("ping", "")
    except ModelsNotTrained:
        models_loaded = False
    except Exception:  # noqa: BLE001 - health must never raise.
        logger.exception("health check: unexpected error during model probe")
        models_loaded = False
    return {"status": "ok", "models_loaded": models_loaded}


@app.post("/triage", response_model=TriageResponse)
def triage(req: TriageRequest) -> TriageResponse:
    # Classify a single issue. Validation errors surface as 422 automatically.
    try:
        result = predict_triage(req.title, req.body)
    except ModelsNotTrained as exc:
        logger.warning("triage requested but models are missing: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="models not trained; run scripts/train_classifier.py",
        ) from exc
    except Exception as exc:  # noqa: BLE001 - safe message, log the detail.
        logger.exception("triage failed unexpectedly")
        raise HTTPException(
            status_code=500, detail="internal error during triage"
        ) from exc

    return TriageResponse(
        label=result["label"],
        confidence=result["label_confidence"],
        severity=result["severity"],
        severity_confidence=result["severity_confidence"],
        top_tokens=result["top_tokens"],
    )


@app.post("/runs")
async def run_pipeline(req: RunRequest) -> dict:
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

    # Gate closed (non-bug) or a dry run → stop here, nothing spent.
    if not passed or not req.live:
        return out

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
    return out


@app.get("/runs/latest")
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
