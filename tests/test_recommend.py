# Tests for the deterministic recommender (pure function, torch-free).

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agenclave.classifier.recommend import recommend  # noqa: E402

_HIGH_CONF = {"label_confidence": 0.9, "severity": None}


def _triage(label, confidence=0.9, severity=None):
    return {"label": label, "label_confidence": confidence, "severity": severity}


def test_bug_can_proceed_with_proceed_rec():
    out = recommend(_triage("bug"))
    assert out["can_proceed_to_stage2"] is True
    assert out["recommendations"]
    kinds = {r["kind"] for r in out["recommendations"]}
    assert "proceed" in kinds


def test_feature_request_cannot_proceed():
    out = recommend(_triage("feature_request"))
    assert out["can_proceed_to_stage2"] is False
    assert out["recommendations"]
    assert "proceed" not in {r["kind"] for r in out["recommendations"]}


def test_documentation_cannot_proceed():
    out = recommend(_triage("documentation"))
    assert out["can_proceed_to_stage2"] is False
    assert out["recommendations"]


def test_question_other_cannot_proceed():
    out = recommend(_triage("question_other"))
    assert out["can_proceed_to_stage2"] is False
    assert out["recommendations"]


def test_low_confidence_prepends_caution():
    out = recommend(_triage("bug", confidence=0.3))
    assert out["recommendations"][0]["kind"] == "caution"
    assert "confidence" in out["recommendations"][0]["title"].lower()
    # Still a bug -> still eligible for Stage 2.
    assert out["can_proceed_to_stage2"] is True


def test_high_confidence_has_no_leading_caution():
    out = recommend(_triage("bug", confidence=0.95))
    assert out["recommendations"][0]["kind"] != "caution"


def test_severity_tunes_wording():
    high = recommend(_triage("bug", severity="high"))
    assert any("urgent" in r["detail"].lower() for r in high["recommendations"])
