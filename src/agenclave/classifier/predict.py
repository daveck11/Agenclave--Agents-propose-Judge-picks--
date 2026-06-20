# Torch-free inference for the served triage classifier.
#
# Loads the persisted production TF-IDF pipeline (`models/type_clf.joblib`) once,
# lazily, and caches it. This module must NOT import torch or
# sentence-transformers, it is the import path used by the FastAPI service, which
# has to stay light.
#
# The shipped deliverable is **type-only**: the severity head is omitted (no
# cleanly licensed source, see data/README.md). If a severity model is present
# (produced by the opt-in `train_classifier.py --with-severity`) it is loaded and
# used; otherwise severity fields come back `None`. The TYPE head is always
# required.
#
# `predict_triage(title, body)` returns the triage schema, including
# `top_tokens`: the TF-IDF tokens that most drive the predicted TYPE class
# (vocabulary x linear coefficients; `feature_importances_` fallback for RF).

from __future__ import annotations

import functools
import json

import joblib
import numpy as np

from ..config import MODELS_DIR

TYPE_MODEL_PATH = MODELS_DIR / "type_clf.joblib"
SEVERITY_MODEL_PATH = MODELS_DIR / "severity_clf.joblib"
METADATA_PATH = MODELS_DIR / "metadata.json"


class ModelsNotTrained(RuntimeError):
    # Raised when the persisted production models are missing.
    pass


def _compose_text(title: str, body: str) -> str:
    title = "" if title is None else str(title)
    body = "" if body is None else str(body)
    return f"{title} {body}".strip()


@functools.lru_cache(maxsize=1)
def _load_models() -> dict:
    # Load + cache the served pipeline(s) and metadata (once per process).
    #
    #     The TYPE model is required. The SEVERITY model is optional: it is loaded only
    #     if present (the shipped deliverable is type-only), otherwise `severity` is
    #     `None` and severity fields are reported as `None` downstream.
    if not TYPE_MODEL_PATH.exists():
        raise ModelsNotTrained(
            f"missing production model: {TYPE_MODEL_PATH} "
            "-- run scripts/train_classifier.py first"
        )
    metadata = {}
    if METADATA_PATH.exists():
        metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    severity_model = (
        joblib.load(SEVERITY_MODEL_PATH) if SEVERITY_MODEL_PATH.exists() else None
    )
    return {
        "type": joblib.load(TYPE_MODEL_PATH),
        "severity": severity_model,
        "metadata": metadata,
    }


def _predict_one(pipeline, text: str) -> tuple[str, float]:
    # Predict label + confidence (max predict_proba) for one text.
    proba = pipeline.predict_proba([text])[0]
    idx = int(np.argmax(proba))
    label = str(pipeline.classes_[idx])
    return label, float(proba[idx])


def _top_tokens(pipeline, predicted_label: str, k: int = 8) -> list[str]:
    # Top-k TF-IDF tokens driving `predicted_label`.
    #
    #     For a linear model, rank by the class's coefficient vector; for a tree
    #     ensemble, fall back to global `feature_importances_`. Returns vocabulary
    #     terms (best-effort; empty list if the estimator exposes neither).
    vectorizer = pipeline.named_steps.get("features")
    clf = pipeline.named_steps.get("clf")
    if vectorizer is None or clf is None:
        return []
    try:
        vocab = vectorizer.get_feature_names_out()
    except Exception:  # noqa: BLE001 - non-text vectorizer
        return []

    weights = None
    if hasattr(clf, "coef_"):
        classes = list(clf.classes_)
        if predicted_label in classes:
            ci = classes.index(predicted_label)
            coef = clf.coef_
            # Binary LR stores a single row; map both classes to it sensibly.
            weights = coef[ci] if coef.shape[0] > 1 else coef[0]
    elif hasattr(clf, "feature_importances_"):
        weights = clf.feature_importances_

    if weights is None:
        return []
    weights = np.asarray(weights).ravel()
    if weights.shape[0] != len(vocab):
        return []
    top_idx = np.argsort(weights)[::-1][:k]
    return [str(vocab[i]) for i in top_idx if weights[i] > 0]


def predict_triage(title: str, body: str = "", top_k: int = 8) -> dict:
    # Classify an issue into type (and severity, if that head is available).
    #
    #     Returns a dict with keys: `label`, `label_confidence`, `severity`,
    #     `severity_confidence`, `top_tokens`. `severity` and
    #     `severity_confidence` are `None` when the (optional) severity head is not
    #     present, the shipped deliverable is type-only.
    models = _load_models()
    text = _compose_text(title, body)

    label, label_conf = _predict_one(models["type"], text)
    if models["severity"] is not None:
        severity, severity_conf = _predict_one(models["severity"], text)
    else:
        severity, severity_conf = None, None
    top_tokens = _top_tokens(models["type"], label, k=top_k)

    return {
        "label": label,
        "label_confidence": label_conf,
        "severity": severity,
        "severity_confidence": severity_conf,
        "top_tokens": top_tokens,
    }
