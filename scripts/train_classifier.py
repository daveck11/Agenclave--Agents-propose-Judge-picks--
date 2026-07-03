#!/usr/bin/env python3
# Train + select the Stage 1 triage classifier(s).
#
# Only the issue-type head ships. By default this trains just that head;
# pass `--with-severity` to also train the severity head (opt-in,
# local experimentation only, the source is citation-only, not shipped; see
# data/README.md). The matching processed CSV must exist first
# (`scripts/prepare_data.py` / `scripts/prepare_data.py --with-severity`).
#
# For each task this trains the 4 configs {tfidf, minilm} x {logreg,
# randomforest}, selects by validation macro-F1, and persists:
#
# - `models/type_clf.joblib` (and `models/severity_clf.joblib` when
#   `--with-severity`), the best TF-IDF pipeline per task (the torch-free
#   production model the API serves).
# - `models/metadata.json`, class lists, chosen configs, embedding lift,
#   and which model is served.
# - `models/_trained_configs.joblib`, every fitted config (incl. MiniLM) plus
#   the deterministic splits, so `scripts/evaluate_classifier.py` can score
#   every config on the held-out test set without retraining. (Internal artifact;
#   contains the MiniLM pipelines, so loading it requires torch.)
#
# Run:
#     .venv\Scripts\python.exe scripts\train_classifier.py
#     .venv\Scripts\python.exe scripts\train_classifier.py --with-severity

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import joblib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agenclave.classifier.train import embedding_lift, train_task  # noqa: E402
from agenclave.config import MODELS_DIR  # noqa: E402

SERVED_FILES = {"type": "type_clf.joblib", "severity": "severity_clf.joblib"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Train + select the Stage 1 triage classifier(s).")
    parser.add_argument(
        "--with-severity",
        action="store_true",
        help="also train the severity head (opt-in; NOT part of the shipped "
        "deliverable). Requires data/processed/severity.csv.",
    )
    args = parser.parse_args()

    tasks = ["type"] + (["severity"] if args.with_severity else [])
    if not args.with_severity:
        print("Training TYPE head only (shipped default). "
              "Pass --with-severity to also train severity (local-only).")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    results = {}
    for task in tasks:
        results[task] = train_task(task)

    # --- Persist the served (best TF-IDF) pipelines + metadata ---------------
    served_files = SERVED_FILES
    metadata = {
        "seed": 42,
        "serving": (
            "Production models are the best TF-IDF pipeline per task: torch-free "
            "and interpretable (top tokens from vocab x coefficients). MiniLM "
            "variants are trained/evaluated for the lift comparison only and are "
            "not persisted for serving."
        ),
        "tasks": {},
    }

    for task in tasks:
        result = results[task]
        served = result.best_tfidf
        out_path = MODELS_DIR / served_files[task]
        joblib.dump(served.pipeline, out_path)
        print(f"\nsaved served model: {out_path}")

        metadata["tasks"][task] = {
            "classes": result.classes,
            "served_model_file": served_files[task],
            "served_config": served.name,
            "served_val_macro_f1": round(served.val_macro_f1, 4),
            "best_overall_config": result.best_overall.name,
            "best_overall_val_macro_f1": round(result.best_overall.val_macro_f1, 4),
            "embedding_lift": embedding_lift(result),
            "all_configs_val_macro_f1": {
                c.name: round(c.val_macro_f1, 4) for c in result.configs
            },
        }

    (MODELS_DIR / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    print(f"saved metadata: {MODELS_DIR / 'metadata.json'}")

    # --- Persist ALL fitted configs + splits for the evaluator ---------------
    cache = {
        task: {
            "classes": results[task].classes,
            "split": results[task].split,
            "configs": [
                {
                    "feature_kind": c.feature_kind,
                    "estimator_kind": c.estimator_kind,
                    "name": c.name,
                    "val_macro_f1": c.val_macro_f1,
                    "pipeline": c.pipeline,
                }
                for c in results[task].configs
            ],
        }
        for task in tasks
    }
    cache_path = MODELS_DIR / "_trained_configs.joblib"
    joblib.dump(cache, cache_path)
    print(f"saved internal eval cache: {cache_path}")

    print(f"\nDone in {time.time() - t0:.1f}s.")


if __name__ == "__main__":
    main()
