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

import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from agenclave.classifier.predict import ModelsNotTrained, predict_triage

from .schemas import TriageRequest, TriageResponse

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
