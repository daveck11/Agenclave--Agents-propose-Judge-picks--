#!/usr/bin/env python3
# Evaluate every trained config on the held-out test set.
#
# Loads `models/_trained_configs.joblib` (produced by train_classifier.py),
# scores all 4 configs per task on the deterministic test split, and writes:
#
# - `results/classifier_metrics.json`, per task & per config: accuracy, macro
#   precision/recall/F1, per-class metrics + support, confusion matrix, plus a
#   top-level summary that makes the TF-IDF-vs-MiniLM lift obvious.
# - `results/cm_type.png` / `results/cm_severity.png`, confusion matrix for
#   each served (production TF-IDF) model.
#
# Run:
#     .venv\Scripts\python.exe scripts\evaluate_classifier.py

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agenclave.config import MODELS_DIR, RESULTS_DIR  # noqa: E402

CACHE_PATH = MODELS_DIR / "_trained_configs.joblib"


def _evaluate(pipeline, X_test, y_test, classes: list[str]) -> dict:
    # Compute full test metrics for one fitted pipeline.
    y_pred = pipeline.predict(X_test)

    accuracy = float(accuracy_score(y_test, y_pred))
    macro_p, macro_r, macro_f1, _ = precision_recall_fscore_support(
        y_test, y_pred, labels=classes, average="macro", zero_division=0
    )
    p, r, f1, support = precision_recall_fscore_support(
        y_test, y_pred, labels=classes, average=None, zero_division=0
    )
    cm = confusion_matrix(y_test, y_pred, labels=classes)

    per_class = {
        cls: {
            "precision": float(p[i]),
            "recall": float(r[i]),
            "f1": float(f1[i]),
            "support": int(support[i]),
        }
        for i, cls in enumerate(classes)
    }
    return {
        "accuracy": accuracy,
        "macro_precision": float(macro_p),
        "macro_recall": float(macro_r),
        "macro_f1": float(macro_f1),
        "per_class": per_class,
        "confusion_matrix": {"labels": list(classes), "matrix": cm.tolist()},
    }


def _plot_cm(cm: np.ndarray, classes: list[str], title: str, dest: Path) -> None:
    # Save a labelled confusion-matrix heatmap.
    fig, ax = plt.subplots(figsize=(1.6 * len(classes) + 2, 1.6 * len(classes) + 2))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(classes)), labels=classes, rotation=45, ha="right")
    ax.set_yticks(range(len(classes)), labels=classes)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title(title)
    thresh = cm.max() / 2.0 if cm.max() else 0.5
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(
                j,
                i,
                str(cm[i, j]),
                ha="center",
                va="center",
                color="white" if cm[i, j] > thresh else "black",
            )
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(dest, dpi=130)
    plt.close(fig)
    print(f"  saved {dest}")


def main() -> None:
    if not CACHE_PATH.exists():
        sys.exit(
            f"ERROR: {CACHE_PATH} not found; run scripts/train_classifier.py first."
        )
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    cache = joblib.load(CACHE_PATH)

    out = {
        "description": (
            "Held-out TEST-set metrics for every trained config per task. The "
            "served production model is the best TF-IDF config (torch-free). "
            "MiniLM configs are reported only to show the embedding lift."
        ),
        "tasks": {},
        "summary": {},
    }
    cm_files = {"type": "cm_type.png", "severity": "cm_severity.png"}

    for task, payload in cache.items():
        classes = payload["classes"]
        split = payload["split"]
        X_test, y_test = split.X_test, split.y_test
        print(f"\n=== Evaluating task: {task} (test n={len(X_test):,}) ===")

        task_out = {"classes": classes, "configs": {}}
        served_metrics = None
        for cfg in payload["configs"]:
            metrics = _evaluate(cfg["pipeline"], X_test, y_test, classes)
            metrics["val_macro_f1"] = float(cfg["val_macro_f1"])
            task_out["configs"][cfg["name"]] = metrics
            print(
                f"  {cfg['name']:<22} test macro-F1={metrics['macro_f1']:.4f} "
                f"acc={metrics['accuracy']:.4f}"
            )
            # Served model = best TF-IDF config by validation macro-F1.
            if cfg["feature_kind"] == "tfidf":
                if served_metrics is None or (
                    cfg["val_macro_f1"] > served_metrics[0]
                ):
                    served_metrics = (cfg["val_macro_f1"], cfg["name"], metrics)

        # Lift summary (best MiniLM vs best TF-IDF, on TEST macro-F1).
        tfidf_cfgs = {
            n: m for n, m in task_out["configs"].items() if n.startswith("tfidf+")
        }
        minilm_cfgs = {
            n: m for n, m in task_out["configs"].items() if n.startswith("minilm+")
        }
        best_tfidf = max(tfidf_cfgs.items(), key=lambda kv: kv[1]["macro_f1"])
        best_minilm = max(minilm_cfgs.items(), key=lambda kv: kv[1]["macro_f1"])
        out["summary"][task] = {
            "served_config": served_metrics[1],
            "served_test_macro_f1": served_metrics[2]["macro_f1"],
            "served_test_accuracy": served_metrics[2]["accuracy"],
            "best_tfidf_config": best_tfidf[0],
            "best_tfidf_test_macro_f1": best_tfidf[1]["macro_f1"],
            "best_minilm_config": best_minilm[0],
            "best_minilm_test_macro_f1": best_minilm[1]["macro_f1"],
            "lift_minilm_minus_tfidf_test_macro_f1": float(
                best_minilm[1]["macro_f1"] - best_tfidf[1]["macro_f1"]
            ),
        }
        out["tasks"][task] = task_out

        # Confusion matrix PNG for the served model.
        cm = np.array(served_metrics[2]["confusion_matrix"]["matrix"])
        _plot_cm(
            cm,
            classes,
            f"{task} (served: {served_metrics[1]})",
            RESULTS_DIR / cm_files[task],
        )

    metrics_path = RESULTS_DIR / "classifier_metrics.json"
    metrics_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nsaved {metrics_path}")
    print("\nSummary (test macro-F1):")
    for task, s in out["summary"].items():
        print(
            f"  {task:<9} served {s['served_config']} "
            f"F1={s['served_test_macro_f1']:.4f} | "
            f"tfidf {s['best_tfidf_test_macro_f1']:.4f} vs "
            f"minilm {s['best_minilm_test_macro_f1']:.4f} "
            f"(lift {s['lift_minilm_minus_tfidf_test_macro_f1']:+.4f})"
        )


if __name__ == "__main__":
    main()
