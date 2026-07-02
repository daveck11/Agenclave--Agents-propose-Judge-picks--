#!/usr/bin/env python3
# Round 5: live verified runs -> real per-model reliability.
#
# For each task that ships with its OWN runnable tests, dispatch to the configured
# agents (live), verify each candidate by applying it and running those tests
# (harness/verify.verify_patch), record the pass/fail into the reliability store
# (harness/reliability.record_outcome), and print the trust ranking. Over many
# runs this accumulates the genuine per-model track record the router draws on.
#
# HONESTY: the trust signal is each task's OWN in-loop tests — NEVER a hidden
# SWE-bench FAIL_TO_PASS grade. This script is the only path that writes reliability
# data, and it only writes what verify_patch actually observed.
#
# Dry-run by default (no API calls). --live dispatches to the provider (spends).
#
#   python scripts/verified_run.py --dry-run
#   python scripts/verified_run.py --live

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agenclave.config import settings  # noqa: E402
from agenclave.harness import Task, build_agents, dispatch  # noqa: E402
from agenclave.harness.reliability import record_outcome, reliability  # noqa: E402
from agenclave.harness.trust import trust_rank  # noqa: E402
from agenclave.harness.verify import verify_patch  # noqa: E402

# Task library: self-contained fixtures, each with its own tests. `category` is the
# task kind (feeds per-category reliability). Grow this list for richer signal.
TASKS = [
    {
        "id": "calc-add",
        "category": "bug",
        "repo": ROOT / "tests" / "fixtures" / "calc_bug" / "repo",
        "test_cmd": [sys.executable, "-m", "pytest", "check_add.py", "-q"],
        "problem_statement": (
            "The function add(a, b) in calc.py returns `a - b` instead of `a + b`. "
            "Fix the bug so addition works correctly."
        ),
    },
    {
        "id": "last-n-off-by-one",
        "category": "bug",
        "repo": ROOT / "tests" / "fixtures" / "off_by_one" / "repo",
        "test_cmd": [sys.executable, "-m", "pytest", "check_seq.py", "-q"],
        "problem_statement": (
            "last_n(items, n) in seq.py should return the last n items, but it is "
            "off by one (it returns n-1 items). Fix it."
        ),
    },
    {
        "id": "mutable-default",
        "category": "bug",
        "repo": ROOT / "tests" / "fixtures" / "mutable_default" / "repo",
        "test_cmd": [sys.executable, "-m", "pytest", "check_acc.py", "-q"],
        "problem_statement": (
            "collect(value, into=[]) in acc.py reuses the same list across calls "
            "(mutable default argument bug); a call with no bucket should start from "
            "an empty list. Fix it."
        ),
    },
    {
        "id": "factorial-base",
        "category": "bug",
        "repo": ROOT / "tests" / "fixtures" / "recursion" / "repo",
        "test_cmd": [sys.executable, "-m", "pytest", "check_mathx.py", "-q"],
        "problem_statement": (
            "factorial(n) in mathx.py infinitely recurses for n=0 (only n==1 is a "
            "base case). factorial(0) should return 1. Fix it."
        ),
    },
]


async def _run_task(t: dict, agents, live: bool) -> None:
    task = Task(
        instance_id=t["id"],
        repo=str(t["repo"]),
        problem_statement=t["problem_statement"],
        triage_label=t["category"],
    )
    print(f"\n=== {t['id']} (category={t['category']}) ===")
    if not live:
        print(f"  DRY RUN — would dispatch to {[a.name for a in agents]}")
        print(f"  and verify each patch with: {' '.join(t['test_cmd'])}")
        return

    candidates = await dispatch(task, agents)
    vrs = {}
    for c in candidates:
        if not c.ok:
            print(f"  {c.agent_name:<46} dispatch=err: {c.error}")
            continue
        vr = verify_patch(c.patch, t["repo"], t["test_cmd"])
        vrs[c.agent_name] = vr
        # Honest: reliability is fed ONLY by this in-loop verification result.
        record_outcome(c.agent_name, t["category"], vr.tests_passed)
        print(f"  {c.agent_name:<46} applies={vr.applies} tests_passed={vr.tests_passed}")

    ranking = trust_rank(candidates, vrs, category=t["category"])
    print("  trust ranking:")
    for i, v in enumerate(ranking, 1):
        print(f"    {i}. {v.agent_name:<44} {v.tier:<18} {v.reason}")


async def _amain(args: argparse.Namespace) -> None:
    models = settings.agent_model_list
    print(f"provider={settings.provider} live={args.live}")
    print(f"models: {models}")
    agents = build_agents(settings.provider, models) if args.live else []
    for t in TASKS:
        await _run_task(t, agents, args.live)

    if args.live:
        print("\nUpdated reliability (category=bug):")
        for m in models:
            est, passed, total = reliability(m, "bug")
            print(f"  {m:<46} {passed}/{total}  est={est:.3f}")
        print("\nWrote results/model_reliability.json - the router now has real data.")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Round 5: live verified runs -> per-model reliability."
    )
    ap.add_argument("--live", action="store_true", help="dispatch to the provider (spends credits)")
    ap.add_argument("--dry-run", action="store_true", help="no API calls (default)")
    args = ap.parse_args()
    if args.dry_run:
        args.live = False
    asyncio.run(_amain(args))


if __name__ == "__main__":
    main()
