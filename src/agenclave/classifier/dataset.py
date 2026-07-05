# Dataset loading + deterministic, leakage-free splits for the two heads.
#
# Two independent classification tasks share one schema:
#
# - `type`     -> `data/processed/issues.csv`   (label    in TYPE_CLASSES)
# - `severity` -> `data/processed/severity.csv` (severity in SEVERITY_CLASSES)
#
# Both CSVs have columns `id, title, body, <label>`. The model text input is
# `title + " " + body` (the severity source has an empty `body`, so that head
# is effectively title-only, documented in the model card).
#
# Splitting is a single deterministic stratified 70/15/15 train/val/test split
# with a fixed seed. Splits are disjoint by row (no leakage); the same class set
# is preserved across all three.

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sklearn.model_selection import train_test_split

from ..config import DATA_DIR

SEED = 42

# Canonical class lists (must match scripts/prepare_data.py / data/README.md).
TYPE_CLASSES = ["bug", "feature_request", "documentation", "question_other"]
SEVERITY_CLASSES = ["low", "medium", "high"]

# Per-task config: CSV filename + label column + canonical class list.
TASKS: dict[str, dict] = {
    "type": {
        "csv": "issues.csv",
        "label_col": "label",
        "classes": TYPE_CLASSES,
    },
    "severity": {
        "csv": "severity.csv",
        "label_col": "severity",
        "classes": SEVERITY_CLASSES,
    },
}


@dataclass
class Split:
    # One deterministic train/val/test split. X_* are text (title + body),
    # y_* are labels, ids_* keep the original row ids so the tests can check
    # for leakage.

    task: str
    classes: list[str]
    X_train: pd.Series
    X_val: pd.Series
    X_test: pd.Series
    y_train: pd.Series
    y_val: pd.Series
    y_test: pd.Series
    ids_train: pd.Series
    ids_val: pd.Series
    ids_test: pd.Series


def _build_text(df: pd.DataFrame) -> pd.Series:
    # Compose the model text column = title + ' ' + body (NaN-safe).
    title = df["title"].fillna("").astype(str)
    body = df["body"].fillna("").astype(str)
    return (title + " " + body).str.strip()


def load_task_frame(task: str) -> pd.DataFrame:
    # Load a task's processed CSV into a DataFrame with a `text` column.
    if task not in TASKS:
        raise ValueError(f"unknown task {task!r}; expected one of {list(TASKS)}")
    cfg = TASKS[task]
    csv_path = DATA_DIR / "processed" / cfg["csv"]
    if not csv_path.exists():
        raise FileNotFoundError(
            f"missing dataset {csv_path}; run scripts/prepare_data.py first"
        )
    df = pd.read_csv(csv_path)
    label_col = cfg["label_col"]
    if label_col not in df.columns:
        raise ValueError(
            f"expected label column {label_col!r} in {csv_path}; got {list(df.columns)}"
        )
    df["text"] = _build_text(df)
    # Drop rows that ended up with no usable text after composition.
    df = df[df["text"].str.strip() != ""].copy()
    # Keep only known classes (defensive; prepare_data already enforces this).
    df = df[df[label_col].isin(cfg["classes"])].copy()
    # Drop exact-duplicate texts before splitting, otherwise the same issue
    # text can land in both train and test and inflate the held-out metrics.
    # Can't dedupe on `id`: it's the per-repo issue number, not globally
    # unique.
    df = df.drop_duplicates(subset="text", keep="first")
    return df.reset_index(drop=True)


def make_split(
    task: str,
    test_size: float = 0.15,
    val_size: float = 0.15,
    seed: int = SEED,
) -> Split:
    # Stratified split, test carved out first and then val from the rest,
    # so the three sets are disjoint and keep the class balance. Fixed seed
    # makes it reproducible.
    cfg = TASKS[task]
    label_col = cfg["label_col"]
    df = load_task_frame(task)

    X = df["text"]
    y = df[label_col]
    ids = df["id"]

    # Stage 1: hold out the test set.
    X_tr_val, X_test, y_tr_val, y_test, ids_tr_val, ids_test = train_test_split(
        X, y, ids, test_size=test_size, random_state=seed, stratify=y
    )
    # Stage 2: split val out of the remainder (rescale so val_size is a fraction
    # of the *original* dataset, not of the remainder).
    rel_val = val_size / (1.0 - test_size)
    X_train, X_val, y_train, y_val, ids_train, ids_val = train_test_split(
        X_tr_val,
        y_tr_val,
        ids_tr_val,
        test_size=rel_val,
        random_state=seed,
        stratify=y_tr_val,
    )

    return Split(
        task=task,
        classes=list(cfg["classes"]),
        X_train=X_train,
        X_val=X_val,
        X_test=X_test,
        y_train=y_train,
        y_val=y_val,
        y_test=y_test,
        ids_train=ids_train,
        ids_val=ids_val,
        ids_test=ids_test,
    )
