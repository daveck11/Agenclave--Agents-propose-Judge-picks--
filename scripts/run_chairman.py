#!/usr/bin/env python3
# Stage 2: run the Chairman best-of-N harness on a SWE-bench Lite slice.
#
# Pipeline per instance:
#   1. Stage 1 triage (the "front door"): classify the issue text and annotate
#      the task with the predicted type. Torch-free; no API key.
#   2. Dispatch: send the task to N agents concurrently (the configured provider).
#   3. Chairman: judge the candidate patches, select/synthesise the best.
#
# Outputs (under results/):
#   - chairman_eval.json         : full log, per-instance candidates + decision,
#                                  the exact instance IDs used, and run config.
#   - preds_chairman.jsonl       : SWE-bench predictions (chairman-selected patch).
#   - preds_<agent>.jsonl        : SWE-bench predictions per agent (for the
#                                  per-agent vs chairman comparison).
#
# HONESTY: this script produces candidate patches and the Chairman's selection. It
# does NOT compute resolve rate itself, a real resolve rate requires applying each
# patch and running the repo's FAIL_TO_PASS tests via the official SWE-bench
# evaluation harness (Docker). Feed the preds_*.jsonl files to that harness to get
# real numbers; nothing here is fabricated.
#
# Cost guardrail: `--dry-run` (the default) makes ZERO paid API calls, it loads
# the slice, runs triage, and prints a cost projection. Add `--live` to actually
# call the provider; combine with `--limit` to bound spend.
#
# Run:
#     python scripts/run_chairman.py --dry-run --limit 2
#     python scripts/run_chairman.py --live --limit 2     # spends API credits

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agenclave.config import RESULTS_DIR, settings  # noqa: E402
from agenclave.harness import Chairman, Task, build_agents, dispatch  # noqa: E402

SWEBENCH_DATASET = "princeton-nlp/SWE-bench_Lite"

# Rough $/1M (input, output) for cost projection only. Real billing differs.
_PRICE_PER_M = {
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.5, 10.0),
}
# Coarse per-call token assumptions for the estimate (issue in, diff out).
_EST_INPUT_TOKENS = 2500
_EST_OUTPUT_TOKENS = 1200


def _load_slice(limit: int, instances: list[str] | None) -> list[Task]:
    # Load a SWE-bench Lite slice as Tasks. Fails loudly if unreachable.
    try:
        from datasets import load_dataset
    except ImportError:
        sys.exit("ERROR: the `datasets` library is required (requirements.txt).")
    try:
        ds = load_dataset(SWEBENCH_DATASET, split="test")
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"ERROR: could not load {SWEBENCH_DATASET}: {exc}")

    tasks: list[Task] = []
    for row in ds:
        if instances and row["instance_id"] not in instances:
            continue
        tasks.append(
            Task(
                instance_id=row["instance_id"],
                repo=row.get("repo", ""),
                problem_statement=row.get("problem_statement", ""),
                base_commit=row.get("base_commit"),
                hints=row.get("hints_text") or None,
            )
        )
        if not instances and len(tasks) >= limit:
            break
    if not tasks:
        sys.exit("ERROR: no instances selected (check --instances / --limit).")
    return tasks


def _triage(task: Task) -> Task:
    # Run the Stage 1 classifier as the front door; annotate the task.
    #
    #     Falls back gracefully (no annotation) if the Stage 1 model isn't trained  -
    #     the harness still runs; the triage is an enhancement, not a hard dependency.
    try:
        from agenclave.classifier.predict import ModelsNotTrained, predict_triage

        pred = predict_triage(task.problem_statement[:2000], "")
    except ModelsNotTrained:
        return task
    except Exception:  # noqa: BLE001 - triage must never break the run
        return task
    # Task is frozen; rebuild with annotations.
    return Task(
        instance_id=task.instance_id,
        repo=task.repo,
        problem_statement=task.problem_statement,
        base_commit=task.base_commit,
        hints=task.hints,
        triage_label=pred.get("label"),
        triage_severity=pred.get("severity"),
        metadata=task.metadata,
    )


def _project_cost(n_tasks: int, models: list[str]) -> None:
    n_calls = n_tasks * (len(models) + 1)  # N agents + 1 chairman per instance
    print("\n--- Cost projection (estimate only) ---")
    print(f"  instances: {n_tasks}")
    print(f"  agents:    {len(models)} ({', '.join(models)})")
    print(f"  chairman:  {settings.chairman_model}")
    print(f"  paid LLM calls (N agents + 1 judge) x {n_tasks} = {n_calls}")
    total = 0.0
    for m in models + [settings.chairman_model]:
        pin, pout = _PRICE_PER_M.get(m, (0.0, 0.0))
        per_call = (_EST_INPUT_TOKENS * pin + _EST_OUTPUT_TOKENS * pout) / 1_000_000
        calls = n_tasks  # each model: one call per instance
        total += per_call * calls
        tag = "" if m in _PRICE_PER_M else "  (price unknown -> $0)"
        print(f"    {m:<20} ~${per_call:.4f}/call x {calls} = ${per_call*calls:.3f}{tag}")
    print(f"  estimated total: ~${total:.3f} "
          f"(@ ~{_EST_INPUT_TOKENS} in / ~{_EST_OUTPUT_TOKENS} out tokens per call)")
    print("  NOTE: rough estimate; real cost depends on issue/diff size.\n")


async def _run_one(task: Task, agents, chairman: Chairman) -> dict:
    candidates = await dispatch(task, agents)
    decision = await chairman.judge(task, candidates)
    selected_patch = ""
    if decision.synthesized_patch:
        selected_patch = decision.synthesized_patch
    elif decision.selected_agent:
        selected_patch = next(
            (c.patch for c in candidates if c.agent_name == decision.selected_agent),
            "",
        )
    return {
        "instance_id": task.instance_id,
        "repo": task.repo,
        "problem_statement": task.problem_statement,
        "triage_label": task.triage_label,
        "candidates": [
            {
                "agent": c.agent_name,
                "ok": c.ok,
                "error": c.error,
                "patch": c.patch,
            }
            for c in candidates
        ],
        "decision": {
            "selected_agent": decision.selected_agent,
            "ranking": decision.ranking,
            "rationale": decision.rationale,
            "synthesized": bool(decision.synthesized_patch),
        },
        "selected_patch": selected_patch,
    }


def _write_predictions(records: list[dict], models: list[str]) -> None:
    # Write SWE-bench-format prediction files (chairman + per-agent).
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    def _dump(path: Path, rows: list[dict]) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        print(f"  wrote {path}")

    chairman_rows = [
        {
            "instance_id": r["instance_id"],
            "model_name_or_path": f"agenclave-chairman/{settings.chairman_model}",
            "model_patch": r["selected_patch"],
        }
        for r in records
    ]
    _dump(RESULTS_DIR / "preds_chairman.jsonl", chairman_rows)

    for m in models:
        agent_name = m if settings.provider == "direct" else f"blackbox:{m}"
        rows = []
        for r in records:
            patch = next(
                (c["patch"] for c in r["candidates"] if c["agent"] == agent_name), ""
            )
            rows.append(
                {
                    "instance_id": r["instance_id"],
                    "model_name_or_path": f"agenclave-agent/{agent_name}",
                    "model_patch": patch,
                }
            )
        safe = m.replace("/", "_").replace(":", "_")
        _dump(RESULTS_DIR / f"preds_{safe}.jsonl", rows)


async def _amain(args: argparse.Namespace) -> None:
    instances = (
        [s.strip() for s in args.instances.split(",") if s.strip()]
        if args.instances
        else None
    )
    models = settings.agent_model_list

    print(f"Agenclave Stage 2 | provider={settings.provider} "
          f"chairman={settings.chairman_model}")
    tasks = _load_slice(args.limit, instances)
    tasks = [_triage(t) for t in tasks]
    print(f"\nLoaded {len(tasks)} instance(s):")
    for t in tasks:
        lbl = f"  [{t.triage_label}]" if t.triage_label else ""
        print(f"  - {t.instance_id} ({t.repo}){lbl}")

    _project_cost(len(tasks), models)

    if not args.live:
        print("DRY RUN (default): no API calls made. Re-run with --live to "
              "dispatch to the provider and spend credits.")
        return

    # Live run.
    agents = build_agents(settings.provider, models)
    chairman = Chairman(settings.chairman_model)
    print(f"LIVE: dispatching {len(tasks)} instance(s) to "
          f"{len(agents)} agent(s) + judge...\n")

    records = []
    for t in tasks:
        print(f"  [{t.instance_id}] dispatching...", flush=True)
        rec = await _run_one(t, agents, chairman)
        sel = rec["decision"]["selected_agent"]
        print(f"  [{t.instance_id}] chairman selected: {sel}")
        records.append(rec)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "dataset": SWEBENCH_DATASET,
        "provider": settings.provider,
        "agent_models": models,
        "chairman_model": settings.chairman_model,
        "instance_ids": [r["instance_id"] for r in records],
        "results": records,
        "resolve_rate_note": (
            "Resolve rate is NOT computed here. Feed the preds_*.jsonl files to "
            "the official SWE-bench evaluation harness (applies patch + runs "
            "FAIL_TO_PASS tests) to obtain real per-agent and chairman numbers."
        ),
    }
    eval_path = RESULTS_DIR / "chairman_eval.json"
    eval_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\n  wrote {eval_path}")
    _write_predictions(records, models)
    print("\nDone. Next: run the official SWE-bench harness on the preds files.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 2: run the Chairman best-of-N harness on a SWE-bench Lite slice.")
    parser.add_argument(
        "--live",
        action="store_true",
        help="actually call the provider (spends API credits). Default is a "
        "dry run that only loads data, triages, and projects cost.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="explicit no-op alias for the default (no API calls).",
    )
    parser.add_argument(
        "--limit", type=int, default=2, help="max instances to run (default 2)"
    )
    parser.add_argument(
        "--instances",
        type=str,
        default="",
        help="comma-separated SWE-bench instance IDs (overrides --limit)",
    )
    args = parser.parse_args()
    if args.dry_run:
        args.live = False
    asyncio.run(_amain(args))


if __name__ == "__main__":
    main()
