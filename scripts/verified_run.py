#!/usr/bin/env python3
# Live verified runs. For each fixture task, dispatch to the configured
# agents, apply and test every candidate with verify_patch, record pass/fail
# into the reliability store, and print the trust ranking. Repeated runs are
# what build up the per-model track record the router uses.
#
# This script is the only thing that writes reliability data, and the signal
# is each task's own tests, not a SWE-bench grade (see reliability.py for
# why that matters).
#
# Dry-run by default so you can't spend credits by accident.
#
#   python scripts/verified_run.py --dry-run
#   python scripts/verified_run.py --live

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agenclave.config import settings  # noqa: E402
from agenclave.fixtures import Fixture, list_fixtures  # noqa: E402
from agenclave.harness import Task, build_agents, dispatch  # noqa: E402
from agenclave.harness.reliability import record_outcome, reliability  # noqa: E402
from agenclave.harness.trust import trust_rank  # noqa: E402
from agenclave.harness.verify import verify_patch  # noqa: E402


async def _run_task(f: Fixture, agents, live: bool, log: list) -> None:
    task = Task(
        instance_id=f.id,
        repo=str(f.repo),
        problem_statement=f.body,
        triage_label=f.category,
    )
    print(f"\n=== {f.id} (category={f.category}) ===")
    if not live:
        print(f"  DRY RUN - would dispatch to {[a.name for a in agents]}")
        print(f"  and verify each patch with: {' '.join(f.test_cmd)}")
        return

    candidates = await dispatch(task, agents)
    vrs = {}
    for c in candidates:
        if not c.ok:
            print(f"  {c.agent_name:<46} dispatch=err: {c.error}")
            log.append({"task": f.id, "agent": c.agent_name, "dispatch_error": c.error})
            continue
        vr = verify_patch(c.patch, f.repo, f.test_cmd)
        vrs[c.agent_name] = vr
        record_outcome(c.agent_name, f.category, vr.tests_passed)
        print(f"  {c.agent_name:<46} applies={vr.applies} tests_passed={vr.tests_passed}")
        # keep enough evidence to explain a failure afterwards
        log.append({
            "task": f.id, "agent": c.agent_name,
            "applies": vr.applies, "tests_passed": vr.tests_passed,
            "passed": vr.passed, "total": vr.total, "error": vr.error,
            "evidence_tail": vr.evidence[-800:],
            "patch": c.patch,
        })

    ranking = trust_rank(candidates, vrs, category=f.category)
    print("  trust ranking:")
    for i, v in enumerate(ranking, 1):
        print(f"    {i}. {v.agent_name:<44} {v.tier:<18} {v.reason}")


async def _amain(args: argparse.Namespace) -> None:
    models = settings.agent_model_list
    print(f"provider={settings.provider} live={args.live}")
    print(f"models: {models}")
    agents = build_agents(settings.provider, models) if args.live else []
    log: list = []
    for f in list_fixtures():
        await _run_task(f, agents, args.live, log)

    if args.live:
        print("\nUpdated reliability (category=bug):")
        for m in models:
            est, passed, total = reliability(m, "bug")
            print(f"  {m:<46} {passed}/{total}  est={est:.3f}")
        log_path = ROOT / "results" / "verified_run_last.json"
        log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")
        print("\nWrote results/model_reliability.json")
        print(f"Wrote {log_path} (per-candidate patches + test evidence)")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Run agents on fixture tasks and record verified reliability."
    )
    ap.add_argument("--live", action="store_true", help="dispatch to the provider (spends credits)")
    ap.add_argument("--dry-run", action="store_true", help="no API calls (default)")
    args = ap.parse_args()
    if args.dry_run:
        args.live = False
    asyncio.run(_amain(args))


if __name__ == "__main__":
    main()
