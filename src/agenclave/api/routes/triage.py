# Stage 1 routes: liveness (`/health`) and single-issue triage (`/triage`).
#
# `/triage` wraps the torch-free `predict_triage` and enriches the result with
# deterministic next-step recommendations + the Stage 2 gate flag.

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ...classifier.predict import ModelsNotTrained, TYPE_MODEL_PATH, predict_triage
from ...classifier.recommend import recommend
from ...config import settings
from ..schemas import Recommendation, TriageRequest, TriageResponse

logger = logging.getLogger("agenclave.api")

router = APIRouter()


@router.get("/health")
def health() -> dict:
    # Liveness probe. Only checks that the model file exists, without loading
    # it: the sklearn import + unpickle is slow on small hosts and used to
    # time out Render's health check and 502 the deploy. The model itself
    # loads lazily on the first real request (warmed in the background).
    models_loaded = TYPE_MODEL_PATH.exists()
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
