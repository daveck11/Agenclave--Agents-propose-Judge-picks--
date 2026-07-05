# JSON store of how often each model's patch has passed verification, keyed
# by (model, category). trust_rank uses it as a tiebreak and the router
# samples from it.
#
# One rule matters here: the only thing allowed to write this store is our
# own in-loop verification (verify_patch). If a held-out grade like the
# SWE-bench harness ever fed it, the routing would be learning from the same
# signal we use to evaluate the system, and the numbers would be worthless.

from __future__ import annotations

import json
from pathlib import Path

from ..config import RESULTS_DIR

STORE_NAME = "model_reliability.json"


def _store_path(path: Path | str | None) -> Path:
    # `path` override exists so tests don't write into the real store
    return Path(path) if path is not None else RESULTS_DIR / STORE_NAME


def _normalize_model(model: str) -> str:
    # dispatch names BlackBox agents "blackbox:<model>"; strip that so the
    # same model reached two ways shares one entry
    model = model or ""
    if model.startswith("blackbox:"):
        model = model[len("blackbox:"):]
    return model.strip()


def _key(model: str, category: str | None) -> str:
    # "<model>|<category>"; category is the triage label, empty if unknown
    return f"{_normalize_model(model)}|{category or ''}"


def _load(path: Path | str | None = None) -> dict:
    # missing or corrupt store just means we start from zero
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
    # `passed` has to come from verify_patch, never from an external grade
    # (see the note at the top of this file)
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
    # Returns (estimate, passed, total). Estimate is Laplace-smoothed,
    # (passed+1)/(total+2), so a model with no data sits at 0.5 instead of
    # 0 or 1. The router draws from Beta with these same counts.
    entry = _load(path).get(_key(model, category), {})
    passed = int(entry.get("passed", 0))
    total = int(entry.get("total", 0))
    estimate = (passed + 1) / (total + 2)
    return estimate, passed, total
