# Per-model reliability - learned from real in-loop verification outcomes.
#
# This is the memory behind "which model do I trust for this task": a JSON store
# of how often each model's patch has actually passed verification, keyed by
# (model, category). `trust_rank` uses it as a TIEBREAK - hard verification
# evidence on the current task always dominates; reliability only orders equals.
#
# CRITICAL - no eval leakage. This store is fed ONLY by the trust mechanism's own
# in-loop verification (`verify_patch` on the project's own tests / a generated
# repro). It must NEVER be seeded from the hidden SWE-bench grade or its derived
# artifacts (results/chairman_eval.json, results/preds_*.jsonl). The official
# grade is a separate, out-of-loop final scorer; mixing it in here would both
# import that conclusion and contaminate the trust loop with the eval signal.

from __future__ import annotations

import json
from pathlib import Path

from ..config import RESULTS_DIR

STORE_NAME = "model_reliability.json"


def _store_path(path: Path | str | None) -> Path:
    # Default to the shared results store; `path` overrides for test isolation.
    return Path(path) if path is not None else RESULTS_DIR / STORE_NAME


def _normalize_model(model: str) -> str:
    # Reliability should be consistent regardless of how a model was reached, so
    # strip the provider tag dispatch prepends (BlackBox agents are named
    # "blackbox:<model>", see providers/blackbox.py). Everything else passes
    # through unchanged.
    model = model or ""
    if model.startswith("blackbox:"):
        model = model[len("blackbox:"):]
    return model.strip()


def _key(model: str, category: str | None) -> str:
    # "<model>|<category>" - category is the Stage 1 triage label (bug/... ), used
    # verbatim; None/"" becomes an empty segment (an honest "uncategorised").
    return f"{_normalize_model(model)}|{category or ''}"


def _load(path: Path | str | None = None) -> dict:
    # Tolerate a missing or corrupt store by starting fresh - reliability is an
    # accumulating best-effort signal, never a source of truth to fail hard on.
    p = _store_path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def record_outcome(
    model: str, category: str | None, passed: bool, *, path: Path | str | None = None
) -> None:
    # Fold one in-loop verification result into the store. `passed` MUST come from
    # verify_patch (VerifyResult.tests_passed), never from an out-of-loop grade.
    p = _store_path(path)
    data = _load(path)
    entry = data.get(_key(model, category), {"passed": 0, "total": 0})
    entry["total"] = int(entry.get("total", 0)) + 1
    if passed:
        entry["passed"] = int(entry.get("passed", 0)) + 1
    data[_key(model, category)] = entry
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def reliability(
    model: str, category: str | None, *, path: Path | str | None = None
) -> tuple[float, int, int]:
    # Return (estimate, passed, total). The estimate is a Beta(1,1)-smoothed pass
    # rate `(passed + 1) / (total + 2)`: honest 0.5 with no data, converging on the
    # true rate as evidence accumulates. This is the exact count pair a later
    # Thompson-sampling router will draw from - Beta(passed+1, total-passed+1).
    entry = _load(path).get(_key(model, category), {})
    passed = int(entry.get("passed", 0))
    total = int(entry.get("total", 0))
    estimate = (passed + 1) / (total + 2)
    return estimate, passed, total
