# Router tests. The router picks the top-k subset that runs, never the
# winner (that stays with verification). These pin the selection contract
# and the explore/exploit behaviour.

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agenclave.harness.reliability import record_outcome  # noqa: E402
from agenclave.harness.router import RouteDecision, route  # noqa: E402

MODELS = ["claude", "gpt", "gemini"]


def _seed_history(store, model, passed, failed):
    for _ in range(passed):
        record_outcome(model, "bug", True, path=store)
    for _ in range(failed):
        record_outcome(model, "bug", False, path=store)


def test_route_returns_k_distinct_models_from_the_set(tmp_path):
    store = tmp_path / "rel.json"
    dec = route("bug", MODELS, 2, rng=np.random.default_rng(0), path=store)
    assert isinstance(dec, RouteDecision)
    assert len(dec.selected) == 2
    assert len(set(dec.selected)) == 2
    assert set(dec.selected) <= set(MODELS)
    # `considered` covers every candidate with evidence fields.
    assert {c["model"] for c in dec.considered} == set(MODELS)


def test_seeded_rng_is_deterministic(tmp_path):
    store = tmp_path / "rel.json"
    _seed_history(store, "claude", 8, 2)
    a = route("bug", MODELS, 2, rng=np.random.default_rng(42), path=store)
    b = route("bug", MODELS, 2, rng=np.random.default_rng(42), path=store)
    assert a.selected == b.selected


def test_explore_exploit_leader_wins_more_but_not_always(tmp_path):
    # A strong-history model should be picked more often than a weak one, yet the
    # weak one must still be explored sometimes - the property greedy selection
    # would violate (it would pick the leader every time).
    store = tmp_path / "rel.json"
    _seed_history(store, "claude", 7, 3)   # strong: 7/10
    _seed_history(store, "gpt", 2, 8)      # weak: 2/10
    rng = np.random.default_rng(7)

    counts = {"claude": 0, "gpt": 0}
    for _ in range(500):
        # top-1 so each round is a single winner-take-all draw between the two.
        dec = route("bug", ["claude", "gpt"], 1, rng=rng, path=store)
        counts[dec.selected[0]] += 1

    assert counts["claude"] > counts["gpt"] > 0


def test_no_data_is_explored_roughly_uniformly(tmp_path):
    # With no history every model is Beta(1,1) (uniform); top-1 selection should
    # spread across all candidates rather than fixating on one.
    store = tmp_path / "rel.json"
    rng = np.random.default_rng(3)
    counts = {m: 0 for m in MODELS}
    for _ in range(300):
        dec = route("bug", MODELS, 1, rng=rng, path=store)
        counts[dec.selected[0]] += 1
    assert all(v > 0 for v in counts.values())  # every model gets explored


def test_k_at_or_above_n_returns_all(tmp_path):
    store = tmp_path / "rel.json"
    dec = route("bug", MODELS, 5, rng=np.random.default_rng(1), path=store)
    assert set(dec.selected) == set(MODELS)


def test_non_positive_k_and_empty_models_raise(tmp_path):
    store = tmp_path / "rel.json"
    with pytest.raises(ValueError):
        route("bug", MODELS, 0, path=store)
    with pytest.raises(ValueError):
        route("bug", [], 1, path=store)


def test_reliability_lookup_honours_store_and_normalisation(tmp_path):
    # "blackbox:claude" and "claude" are the same model; history recorded under one
    # prefix must inform routing for the other (reliability._normalize_model).
    store = tmp_path / "rel.json"
    _seed_history(store, "blackbox:claude", 20, 0)  # near-certain winner
    _seed_history(store, "gpt", 0, 20)              # near-certain loser
    rng = np.random.default_rng(11)
    wins = 0
    for _ in range(50):
        dec = route("bug", ["claude", "gpt"], 1, rng=rng, path=store)
        wins += dec.selected[0] == "claude"
    assert wins >= 45  # the merged strong history dominates selection
