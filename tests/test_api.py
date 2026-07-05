# API contract tests for the triage service. Torch-free. The happy path
# adapts to model state: with the trained models present it asserts a real
# 200 prediction, without them a clean 503.

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agenclave.api.main import app  # noqa: E402
from agenclave.classifier.dataset import (  # noqa: E402
    SEVERITY_CLASSES,
    TYPE_CLASSES,
)

client = TestClient(app)

# The shipped deliverable is type-only: only the TYPE model is required for a
# live prediction. The severity model is optional (opt-in, not shipped).
MODELS_EXIST = (ROOT / "models" / "type_clf.joblib").exists()


# --- /health ------------------------------------------------------------------
def test_health_ok_shape():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert isinstance(body["models_loaded"], bool)
    # models_loaded must reflect actual disk state.
    assert body["models_loaded"] is MODELS_EXIST


# --- /triage validation (422) -------------------------------------------------
def test_triage_rejects_empty_title_and_body():
    resp = client.post("/triage", json={"title": "   ", "body": ""})
    assert resp.status_code == 422


def test_triage_rejects_missing_title():
    resp = client.post("/triage", json={"body": "some text"})
    assert resp.status_code == 422


def test_triage_rejects_overly_long_input():
    resp = client.post("/triage", json={"title": "x" * 20_001})
    assert resp.status_code == 422


# --- /triage happy path (state-dependent) -------------------------------------
def test_triage_happy_path_or_503():
    payload = {
        "title": "App crashes on launch",
        "body": "Stack trace shows a null pointer exception on startup.",
    }
    resp = client.post("/triage", json=payload)

    if not MODELS_EXIST:
        assert resp.status_code == 503
        assert "not trained" in resp.json()["detail"].lower()
        return

    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {
        "label",
        "confidence",
        "severity",
        "severity_confidence",
        "top_tokens",
        "recommendations",
        "can_proceed_to_stage2",
    }
    assert body["label"] in TYPE_CLASSES
    assert 0.0 <= body["confidence"] <= 1.0
    assert isinstance(body["top_tokens"], list)
    assert all(isinstance(tok, str) for tok in body["top_tokens"])
    # Stage 3 enrichment: deterministic recommendations + the Stage 2 gate flag.
    assert isinstance(body["recommendations"], list) and body["recommendations"]
    assert all({"title", "detail", "kind"} <= set(r) for r in body["recommendations"])
    assert isinstance(body["can_proceed_to_stage2"], bool)
    # Only a bug is eligible for Stage 2.
    assert body["can_proceed_to_stage2"] is (body["label"] == "bug")
    # Severity is optional (type-only deliverable): either a valid class with a
    # [0,1] confidence, or null/null when the severity head is not present.
    if body["severity"] is None:
        assert body["severity_confidence"] is None
    else:
        assert body["severity"] in SEVERITY_CLASSES
        assert 0.0 <= body["severity_confidence"] <= 1.0
