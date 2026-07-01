# Bucket 1: trust_rank orders candidates by verified trustworthiness, not by looks.

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agenclave.harness.interfaces import PatchResult  # noqa: E402
from agenclave.harness.trust import (  # noqa: E402
    APPLIES_BUT_FAILS,
    BROKEN,
    TRUSTED,
    trust_rank,
)
from agenclave.harness.verify import verify_patch  # noqa: E402

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
