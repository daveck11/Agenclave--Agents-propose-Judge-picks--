# Stage 1 routes: liveness (`/health`) and single-issue triage (`/triage`).
#
# `/triage` wraps the torch-free `predict_triage` and enriches the result with
# deterministic next-step recommendations + the Stage 2 gate flag.

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ...classifier.predict import ModelsNotTrained, predict_triage
from ...classifier.recommend import recommend
from ...config import settings
from ..schemas import Recommendation, TriageRequest, TriageResponse

logger = logging.getLogger("agenclave.api")

router = APIRouter()


@router.get("/health")
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
    # Whether live Stage 2 dispatch can work (a provider key is configured). The UI
    # hides the Live toggle when this is false (e.g. a public demo with no keys).
    if settings.provider == "blackbox":
        live_enabled = bool(settings.blackbox_api_key)
    else:
        live_enabled = bool(settings.anthropic_api_key or settings.openai_api_key)
    return {"status": "ok", "models_loaded": models_loaded, "live_enabled": live_enabled}


@router.post("/triage", response_model=TriageResponse)
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

    advice = recommend(result)
    return TriageResponse(
        label=result["label"],
        confidence=result["label_confidence"],
        severity=result["severity"],
        severity_confidence=result["severity_confidence"],
        top_tokens=result["top_tokens"],
        recommendations=[Recommendation(**r) for r in advice["recommendations"]],
        can_proceed_to_stage2=advice["can_proceed_to_stage2"],
    )
