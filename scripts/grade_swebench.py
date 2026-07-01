#!/usr/bin/env python3
# Grade Stage 2 predictions with the OFFICIAL SWE-bench harness (Docker) and write
# a normalized resolve-rate summary the web app displays.
#
# This is the ONLY place a real resolve rate is produced. It runs on YOUR machine
# with Docker; the result (results/resolve_rate.json) is committed and served read-
# only by the app, so opening the live link never runs Docker (see api .../runs.py
# GET /resolve-rate).
#
# Prereqs:
#   - Docker Desktop running (WSL2 backend on Windows), a few CPUs + 8GB+ RAM,
#     and disk headroom (each instance image is ~1-2 GB).
#   - pip install swebench
#   - preds_*.jsonl files in results/ (produced by scripts/run_chairman.py --live).
#
# Usage:
#   python scripts/grade_swebench.py --plan            # print the commands only (no Docker)
#   python scripts/grade_swebench.py --run-id demo1    # actually grade (needs Docker)
#   python scripts/grade_swebench.py --max-workers 4
#
# HONESTY: numbers come straight from the harness report. The denominator is the
# instance count in each preds file. Nothing is self-scored or fabricated; if you
# never run this, the app simply shows no resolve rate.

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "results"
DATASET = "princeton-nlp/SWE-bench_Lite"


def _system_name(preds: Path) -> str:
    # preds_chairman.jsonl -> "chairman"; preds_gpt-4o-mini.jsonl -> "gpt-4o-mini"
    return preds.stem[len("preds_") :] if preds.stem.startswith("preds_") else preds.stem


def _label(name: str) -> str:
    return "Chairman best-of-N" if name == "chairman" else f"{name} (single agent)"


def _discover_preds() -> list[Path]:
    files = sorted(RESULTS_DIR.glob("preds_*.jsonl"))
    # Chairman first (it's the headline), then the per-agent baselines.
    files.sort(key=lambda p: (_system_name(p) != "chairman", p.name))
    return files


def _instance_count(preds: Path) -> int:
    return sum(1 for line in preds.read_text(encoding="utf-8").splitlines() if line.strip())


def _harness_cmd(preds: Path, run_id: str, max_workers: int) -> list[str]:
    return [
        sys.executable, "-m", "swebench.harness.run_evaluation",
        "--dataset_name", DATASET,
        "--predictions_path", str(preds),
        "--max_workers", str(max_workers),
        "--run_id", run_id,
    ]


def _is_report(data: object) -> bool:
    return isinstance(data, dict) and ("resolved_instances" in data or "resolved_ids" in data)


def _find_report(run_id: str) -> dict | None:
    # The harness writes a report json into the working dir (name usually includes
    # the run_id). Prefer run_id-matching files; fall back to the newest report-
    # shaped json so we're robust to filename changes across swebench versions.
    run_matches = sorted(
        ROOT.glob(f"*{run_id}*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    everything = sorted(
        ROOT.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    for p in [*run_matches, *everything]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if _is_report(data):
            return data
    return None


def _resolved_count(report: dict) -> tuple[int, list[str]]:
    ids = report.get("resolved_ids") or []
    resolved = report.get("resolved_instances")
    if resolved is None:
        resolved = len(ids)
    return int(resolved), list(ids)


def main() -> None:
    ap = argparse.ArgumentParser(description="Grade Stage 2 preds with the official SWE-bench harness.")
    ap.add_argument("--run-id", default="agenclave", help="base run id for the harness (default: agenclave)")
    ap.add_argument("--max-workers", type=int, default=4)
    ap.add_argument("--plan", action="store_true", help="print the harness commands and exit (no Docker)")
    args = ap.parse_args()

    preds_files = _discover_preds()
    if not preds_files:
        sys.exit("ERROR: no results/preds_*.jsonl found. Run scripts/run_chairman.py --live first.")

    if args.plan:
        print("Planned grading commands (run with Docker available):\n")
        for preds in preds_files:
            name = _system_name(preds)
            print(f"  # {_label(name)}  (n={_instance_count(preds)})")
            print("  " + " ".join(_harness_cmd(preds, f"{args.run_id}-{name}", args.max_workers)))
            print()
        print("Then re-run without --plan to grade and write results/resolve_rate.json.")
        return

    out_path = RESULTS_DIR / "resolve_rate.json"

    # Resume support: results are written after EACH system, so an interrupted
    # grade (e.g. the foreground time cap) can be re-run and continues where it
    # left off. Reuse only systems recorded for THIS run_id; a different run_id
    # (or the old demo run) starts fresh and the first save overwrites the file.
    systems = []
    done = set()
    if out_path.exists():
        try:
            prev = json.loads(out_path.read_text(encoding="utf-8"))
            if prev.get("run_id") == args.run_id and prev.get("dataset") == DATASET:
                systems = prev.get("systems", [])
                done = {s["name"] for s in systems}
        except (OSError, json.JSONDecodeError):
            pass

    def _save() -> None:
        out_path.write_text(
            json.dumps(
                {
                    "dataset": DATASET,
                    "harness": "swebench.harness.run_evaluation",
                    "graded_at": datetime.now(timezone.utc).isoformat(),
                    "run_id": args.run_id,
                    "total": max((s["total"] for s in systems), default=0),
                    "systems": systems,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    for preds in preds_files:
        name = _system_name(preds)
        if name in done:
            print(f"=== skip {_label(name)} (already graded) ===")
            continue
        run_id = f"{args.run_id}-{name}"
        total = _instance_count(preds)
        print(f"\n=== Grading {_label(name)}  (n={total}) ===", flush=True)
        try:
            subprocess.run(_harness_cmd(preds, run_id, args.max_workers), check=True, cwd=str(ROOT))
        except FileNotFoundError:
            sys.exit("ERROR: could not run swebench. Install it: pip install swebench")
        except subprocess.CalledProcessError as exc:
            sys.exit(f"ERROR: the SWE-bench harness failed ({exc}). Is Docker running?")

        report = _find_report(run_id)
        if report is None:
            print(f"  WARNING: no report found for run_id={run_id}; skipping {name}")
            continue
        resolved, ids = _resolved_count(report)
        print(f"  -> {name}: resolved {resolved}/{total}")
        systems.append(
            {
                "name": name,
                "label": _label(name),
                "resolved": resolved,
                "total": total,
                "resolved_ids": ids,
            }
        )
        _save()  # incremental: progress survives an interruption

    if not systems:
        sys.exit("ERROR: nothing graded (no reports parsed).")

    print("\n--- Resolve rate (official SWE-bench harness) ---")
    for s in systems:
        print(f"  {s['label']:<40} {s['resolved']}/{s['total']}")
    print(f"\n  wrote {out_path}  ({len(systems)} systems)")


if __name__ == "__main__":
    main()
