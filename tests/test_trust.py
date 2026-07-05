# trust_rank should order candidates by what verification showed.

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agenclave.harness import trust as trust_mod  # noqa: E402
from agenclave.harness.interfaces import PatchResult  # noqa: E402
from agenclave.harness.trust import (  # noqa: E402
    APPLIES_BUT_FAILS,
    BROKEN,
    TRUSTED,
    trust_rank,
)
from agenclave.harness.verify import VerifyResult, verify_patch  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "calc_bug"
REPO = FIX / "repo"
TEST_CMD = [sys.executable, "-m", "pytest", "check_add.py", "-q"]


def _patch(name: str) -> str:
    return (FIX / "patches" / name).read_text(encoding="utf-8")


def _candidate(agent: str, diff: str) -> PatchResult:
    return PatchResult(agent_name=agent, instance_id="calc-add", patch=_patch(diff))


def test_ranking_orders_by_verification():
    cands = [
        _candidate("wrong", "wrong.diff"),
        _candidate("correct", "correct.diff"),
        _candidate("broken", "broken.diff"),
    ]
    vrs = {c.agent_name: verify_patch(c.patch, REPO, TEST_CMD) for c in cands}
    ranking = trust_rank(cands, vrs)

    assert [v.agent_name for v in ranking] == ["correct", "wrong", "broken"]
    tiers = {v.agent_name: v.tier for v in ranking}
    assert tiers == {"correct": TRUSTED, "wrong": APPLIES_BUT_FAILS, "broken": BROKEN}
    assert ranking[0].score == 1.0
    assert "tests pass" in ranking[0].reason


def _passing(agent: str, patch: str) -> tuple[PatchResult, VerifyResult]:
    # A synthetic TRUSTED candidate (applies + all tests pass), no fixture run.
    return (
        PatchResult(agent_name=agent, instance_id="calc-add", patch=patch),
        VerifyResult(applies=True, tests_passed=True, passed=1, total=1, evidence="ok"),
    )


def test_reliability_breaks_ties_over_minimality(monkeypatch):
    # Two candidates are equally TRUSTED on THIS task. `hi` has a *longer* patch
    # (would lose on minimality) but a better track record - reliability must win,
    # proving it outranks minimality while tier stays primary.
    rel = {"hi": (0.9, 9, 10), "lo": (0.2, 2, 10)}
    monkeypatch.setattr(trust_mod, "_reliability", lambda name, cat: rel[name])

    hi, hi_vr = _passing("hi", "a" * 200)  # longer diff
    lo, lo_vr = _passing("lo", "b" * 10)   # shorter diff
    ranking = trust_rank(
        [lo, hi], {"hi": hi_vr, "lo": lo_vr}, category="bug"
    )

    assert [v.agent_name for v in ranking] == ["hi", "lo"]
    assert ranking[0].reliability == 0.9 and ranking[0].reliability_n == 10
    assert "9/10" in ranking[0].reason  # evidence surfaced in the reason


def test_reliability_never_overrides_verification_tier(monkeypatch):
    # A high-reliability BROKEN patch must still rank below a low-reliability
    # TRUSTED one - hard evidence on the current task dominates.
    rel = {"trusted_lo": (0.1, 1, 10), "broken_hi": (0.99, 99, 100)}
    monkeypatch.setattr(trust_mod, "_reliability", lambda name, cat: rel[name])

    good, good_vr = _passing("trusted_lo", "x" * 20)
    bad = PatchResult(agent_name="broken_hi", instance_id="calc-add", patch="junk")
    bad_vr = VerifyResult(False, False, 0, 0, "", error="patch did not apply")
    ranking = trust_rank(
        [bad, good], {"trusted_lo": good_vr, "broken_hi": bad_vr}, category="bug"
    )

    assert ranking[0].agent_name == "trusted_lo"
    assert ranking[0].tier == TRUSTED


def test_no_track_record_is_stated_honestly(monkeypatch):
    monkeypatch.setattr(trust_mod, "_reliability", lambda name, cat: (0.5, 0, 0))
    cand, vr = _passing("fresh", "z" * 10)
    ranking = trust_rank([cand], {"fresh": vr}, category="bug")
    assert "no track record yet" in ranking[0].reason
    assert ranking[0].reliability_n == 0


def test_weak_triage_confidence_annotates_verdicts(monkeypatch):
    monkeypatch.setattr(trust_mod, "_reliability", lambda name, cat: (0.5, 0, 0))
    cand, vr = _passing("a", "z" * 10)
    ranking = trust_rank(
        [cand], {"a": vr}, category="bug", triage_confidence=0.30
    )
    assert "caution" in ranking[0].reason.lower()
    # Strong confidence adds no caution.
    ranking2 = trust_rank(
        [cand], {"a": vr}, category="bug", triage_confidence=0.95
    )
    assert "caution" not in ranking2[0].reason.lower()
