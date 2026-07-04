# Training + model selection for both heads.
#
# For each task we train the cross product
# `{tfidf, minilm} x {logreg, randomforest}` (4 configs) with fixed seeds,
# select the best config by macro-F1 on the validation set, and persist the best
# **TF-IDF** config per task as the torch-free production model.
#
# Why the served model is always TF-IDF (not whichever wins macro-F1):
# - the FastAPI service must import without torch / sentence-transformers, and
# - TF-IDF + a linear model yields interpretable top tokens for the response.
# The MiniLM configs are still trained and evaluated so the model card can report
# the (real) embedding lift; they are simply not persisted for serving.

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.pipeline import Pipeline

from .dataset import Split, make_split
from .features import MiniLMEmbedder, make_tfidf_vectorizer

SEED = 42

FEATURE_KINDS = ("tfidf", "minilm")
ESTIMATOR_KINDS = ("logreg", "randomforest")


def _make_estimator(kind: str):
    # Construct a fresh estimator (fixed seed) for `kind`.
    if kind == "logreg":
        return LogisticRegression(max_iter=2000, C=10.0, random_state=SEED, n_jobs=-1)
    if kind == "randomforest":
        return RandomForestClassifier(
            n_estimators=300, n_jobs=-1, random_state=SEED
        )
    raise ValueError(f"unknown estimator kind {kind!r}")


def build_pipeline(feature_kind: str, estimator_kind: str) -> Pipeline:
    # Build a sklearn Pipeline for one (feature, estimator) config.
    if feature_kind == "tfidf":
        features = make_tfidf_vectorizer()
    elif feature_kind == "minilm":
        features = MiniLMEmbedder()
    else:
        raise ValueError(f"unknown feature kind {feature_kind!r}")
    return Pipeline([("features", features), ("clf", _make_estimator(estimator_kind))])


@dataclass
class TrainedConfig:
    # A fitted config + its validation macro-F1 (for selection).

    task: str
    feature_kind: str
    estimator_kind: str
    pipeline: Pipeline
    val_macro_f1: float

    @property
    def name(self) -> str:
        return f"{self.feature_kind}+{self.estimator_kind}"


@dataclass
class TaskResult:
    # All trained configs for a task plus the selected best / best-TF-IDF.

    task: str
    classes: list[str]
    split: Split
    configs: list[TrainedConfig] = field(default_factory=list)

    @property
    def best_overall(self) -> TrainedConfig:
        return max(self.configs, key=lambda c: c.val_macro_f1)

    @property
    def best_tfidf(self) -> TrainedConfig:
        tfidf = [c for c in self.configs if c.feature_kind == "tfidf"]
        return max(tfidf, key=lambda c: c.val_macro_f1)


def train_task(task: str, *, verbose: bool = True) -> TaskResult:
    # Train all 4 configs for `task` and score them on the val set.
    split = make_split(task, seed=SEED)
    classes = split.classes
    result = TaskResult(task=task, classes=classes, split=split)

    if verbose:
        print(f"\n=== Task: {task} ({len(classes)} classes) ===")
        print(
            f"  rows: train={len(split.X_train):,} "
            f"val={len(split.X_val):,} test={len(split.X_test):,}"
        )

    for feature_kind in FEATURE_KINDS:
        for estimator_kind in ESTIMATOR_KINDS:
            pipe = build_pipeline(feature_kind, estimator_kind)
            if verbose:
                print(f"  training {feature_kind}+{estimator_kind} ...", flush=True)
            pipe.fit(split.X_train, split.y_train)
            val_pred = pipe.predict(split.X_val)
            val_f1 = f1_score(split.y_val, val_pred, labels=classes, average="macro")
            result.configs.append(
                TrainedConfig(
                    task=task,
                    feature_kind=feature_kind,
                    estimator_kind=estimator_kind,
                    pipeline=pipe,
                    val_macro_f1=float(val_f1),
                )
            )
            if verbose:
                print(f"    val macro-F1 = {val_f1:.4f}")

    if verbose:
        best = result.best_overall
        best_tfidf = result.best_tfidf
        print(
            f"  best overall: {best.name} (val macro-F1 {best.val_macro_f1:.4f}); "
            f"served (best tfidf): {best_tfidf.name} "
            f"(val macro-F1 {best_tfidf.val_macro_f1:.4f})"
        )
    return result


def embedding_lift(result: TaskResult) -> dict:
    # Best-MiniLM minus best-TF-IDF val macro-F1 (the transformer lift).
    tfidf = [c for c in result.configs if c.feature_kind == "tfidf"]
    minilm = [c for c in result.configs if c.feature_kind == "minilm"]
    best_tfidf = max(tfidf, key=lambda c: c.val_macro_f1)
    best_minilm = max(minilm, key=lambda c: c.val_macro_f1)
    return {
        "best_tfidf_config": best_tfidf.name,
        "best_tfidf_val_macro_f1": best_tfidf.val_macro_f1,
        "best_minilm_config": best_minilm.name,
        "best_minilm_val_macro_f1": best_minilm.val_macro_f1,
        "lift_minilm_minus_tfidf": float(
            best_minilm.val_macro_f1 - best_tfidf.val_macro_f1
        ),
    }
