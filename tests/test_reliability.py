# Bucket 2A: per-model reliability learned from in-loop verification outcomes.
#
# Reliability is a Beta(1,1)-smoothed pass rate per (model, category), fed ONLY by
# the trust loop's own verification - never by any out-of-loop SWE-bench grade.

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agenclave.harness.reliability import (  # noqa: E402
    _normalize_model,
    record_outcome,
    reliability,
)


def test_smoothing_is_honest_with_no_data(tmp_path):
    store = tmp_path / "rel.json"
    est, passed, total = reliability("claude", "bug", path=store)
    assert (passed, total) == (0, 0)
    assert est == 0.5  # Beta(1,1): (0+1)/(0+2)


def test_estimate_moves_with_evidence(tmp_path):
    store = tmp_path / "rel.json"
    for passed in (True, True, False):  # 2/3
        record_outcome("claude", "bug", passed, path=store)
    est, passed, total = reliability("claude", "bug", path=store)
    assert (passed, total) == (2, 3)
    assert est == (2 + 1) / (3 + 2)  # 0.6, smoothed toward the data


def test_record_outcome_accumulates_and_persists(tmp_path):
    store = tmp_path / "rel.json"
    record_outcome("gpt", "bug", True, path=store)
    record_outcome("gpt", "bug", False, path=store)
    # A fresh read (no in-memory state) sees the persisted counts.
    est, passed, total = reliability("gpt", "bug", path=store)
    assert (passed, total) == (1, 2)
    assert store.exists()


def test_reliability_is_keyed_by_category(tmp_path):
    store = tmp_path / "rel.json"
    record_outcome("claude", "bug", True, path=store)
    record_outcome("claude", "documentation", False, path=store)
    assert reliability("claude", "bug", path=store)[1:] == (1, 1)
    assert reliability("claude", "documentation", path=store)[1:] == (0, 1)


def test_normalize_strips_blackbox_prefix():
    assert _normalize_model("blackbox:anthropic/claude") == "anthropic/claude"
    assert _normalize_model("claude-sonnet-4-6") == "claude-sonnet-4-6"


def test_provider_prefix_is_collapsed_in_store(tmp_path):
    # "blackbox:claude" and "claude" are the same model - counts must merge.
    store = tmp_path / "rel.json"
    record_outcome("blackbox:claude", "bug", True, path=store)
    record_outcome("claude", "bug", True, path=store)
    assert reliability("claude", "bug", path=store)[1:] == (2, 2)


def test_missing_and_corrupt_store_are_tolerated(tmp_path):
    missing = tmp_path / "nope.json"
    assert reliability("x", "bug", path=missing) == (0.5, 0, 0)
    corrupt = tmp_path / "bad.json"
    corrupt.write_text("{not json", encoding="utf-8")
    assert reliability("x", "bug", path=corrupt) == (0.5, 0, 0)
    # A corrupt store recovers on the next write rather than raising.
    record_outcome("x", "bug", True, path=corrupt)
    assert reliability("x", "bug", path=corrupt)[1:] == (1, 1)
