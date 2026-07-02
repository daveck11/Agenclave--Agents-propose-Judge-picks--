#!/usr/bin/env python3
# Bucket 1 demo: verification-backed trust ranking on the controlled calc_bug
# fixture. Runs each candidate patch through verify + trust_rank and prints the
# ranking with evidence - the core thesis, no agents / no network.
#
#     python scripts/demo_trust.py

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import tempfile  # noqa: E402

from agenclave.harness import reliability as rel  # noqa: E402
from agenclave.harness import trust as trust_mod  # noqa: E402
from agenclave.harness.interfaces import PatchResult  # noqa: E402
from agenclave.harness.trust import trust_rank  # noqa: E402
from agenclave.harness.verify import verify_patch  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "calc_bug"
REPO = FIX / "repo"
TEST_CMD = [sys.executable, "-m", "pytest", "check_add.py", "-q"]
CATEGORY = "bug"  # the Stage 1 triage label for this fixture

# Three "agents" produce three candidate patches for the same task.
CANDIDATES = [
    ("gpt-5.4", "wrong.diff"),
    ("claude-sonnet-4.6", "correct.diff"),
    ("gemini-3.1-flash-lite", "broken.diff"),
]

# A little prior history so the reliability column has something to show. Seeded
# ONLY from in-loop verification outcomes (here, a demo fixture) - never from any
# SWE-bench grade. Each tuple: (model, passed, failed) of past verified runs.
PRIOR_HISTORY = [
    ("claude-sonnet-4.6", 2, 8),  # resolved 2/10 historically
    ("gpt-5.4", 1, 9),
    ("gemini-3.1-flash-lite", 0, 10),
]


def main() -> None:
    # Isolate the demo store in a temp dir so we never touch the real results file.
    with tempfile.TemporaryDirectory() as tmp:
        store = f"{tmp}/model_reliability.json"

        # Point trust_rank's reliability lookup at the demo store (it binds the
        # function as trust._reliability at import time, so patch that name).
        trust_mod._reliability = lambda name, cat: rel.reliability(name, cat, path=store)

        for model, passed, failed in PRIOR_HISTORY:
            for _ in range(passed):
                rel.record_outcome(model, CATEGORY, True, path=store)
            for _ in range(failed):
                rel.record_outcome(model, CATEGORY, False, path=store)

        cands, vrs = [], {}
        for name, pf in CANDIDATES:
            patch = (FIX / "patches" / pf).read_text(encoding="utf-8")
            cands.append(PatchResult(agent_name=name, instance_id="calc-add", patch=patch))
            vr = verify_patch(patch, REPO, TEST_CMD)
            vrs[name] = vr
            # Fold THIS run's in-loop outcome back into the store - the trust loop
            # learning from its own verification, the only signal it may use.
            rel.record_outcome(name, CATEGORY, vr.tests_passed, path=store)

        print("Task: fix add(a, b) so it returns a + b")
        print("Which agent's patch do we trust? Verified, not guessed:\n")
        print(f"{'#':<3}{'agent':<26}{'tier':<20}{'reliability':<14}reason")
        ranking = trust_rank(cands, vrs, category=CATEGORY)
        for i, v in enumerate(ranking, 1):
            rel_col = f"{v.reliability:.2f} (n={v.reliability_n})"
            print(f"{i:<3}{v.agent_name:<26}{v.tier:<20}{rel_col:<14}{v.reason}")
        print(f"\nTrusted pick -> {ranking[0].agent_name}")
        print("(tier is primary - reliability only breaks ties among equals)")


if __name__ == "__main__":
    main()
