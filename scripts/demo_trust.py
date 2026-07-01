#!/usr/bin/env python3
# Bucket 1 demo: verification-backed trust ranking on the controlled calc_bug
# fixture. Runs each candidate patch through verify + trust_rank and prints the
# ranking with evidence — the core thesis, no agents / no network.
#
#     python scripts/demo_trust.py

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agenclave.harness.interfaces import PatchResult  # noqa: E402
from agenclave.harness.trust import trust_rank  # noqa: E402
from agenclave.harness.verify import verify_patch  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "calc_bug"
REPO = FIX / "repo"
TEST_CMD = [sys.executable, "-m", "pytest", "check_add.py", "-q"]

# Three "agents" produce three candidate patches for the same task.
CANDIDATES = [
    ("gpt-5.4", "wrong.diff"),
    ("claude-sonnet-4.6", "correct.diff"),
    ("gemini-3.1-flash-lite", "broken.diff"),
]


def main() -> None:
    cands, vrs = [], {}
    for name, pf in CANDIDATES:
        patch = (FIX / "patches" / pf).read_text(encoding="utf-8")
        cands.append(PatchResult(agent_name=name, instance_id="calc-add", patch=patch))
        vrs[name] = verify_patch(patch, REPO, TEST_CMD)

    print("Task: fix add(a, b) so it returns a + b")
    print("Which agent's patch do we trust? Verified, not guessed:\n")
    print(f"{'#':<3}{'agent':<26}{'tier':<20}reason")
    ranking = trust_rank(cands, vrs)
    for i, v in enumerate(ranking, 1):
        print(f"{i:<3}{v.agent_name:<26}{v.tier:<20}{v.reason}")
    print(f"\nTrusted pick -> {ranking[0].agent_name}")


if __name__ == "__main__":
    main()
