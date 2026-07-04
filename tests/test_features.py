# Tests for the Stage 1 classifier feature pipeline, splits, and inference.
#
# Fast by design: no MiniLM download/encode happens here (the embedding path is
# guarded behind a skip). The TF-IDF pipeline and the deterministic split are
# exercised on the real processed CSVs; `predict_triage` is exercised against
# the persisted production models (skipped with a clear message if absent).

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agenclave.classifier.dataset import (  # noqa: E402
    SEVERITY_CLASSES,
    TYPE_CLASSES,
    make_split,
)
from agenclave.classifier.features import make_tfidf_vectorizer  # noqa: E402

# Shipped deliverable is type-only: the type dataset is what the core path needs.
DATA_READY = (ROOT / "data" / "processed" / "issues.csv").exists()
# Severity data is optional (opt-in, not shipped).
SEVERITY_DATA_READY = (ROOT / "data" / "processed" / "severity.csv").exists()

requires_data = pytest.mark.skipif(
    not DATA_READY, reason="processed type dataset missing; run scripts/prepare_data.py"
)


# --- TF-IDF pipeline ----------------------------------------------------------
def test_tfidf_fit_transform_shape_and_vocab():
    corpus = [
        "App crashes on startup with a null pointer error",
        "Please add a dark mode feature to the settings page",
        "The README is missing install instructions",
        "How do I configure the proxy for downloads?",
    ]
    vec = make_tfidf_vectorizer(min_df=1)
    X = vec.fit_transform(corpus)
    assert X.shape[0] == len(corpus)
    assert X.shape[1] > 0
    assert len(vec.get_feature_names_out()) == X.shape[1]
    # ngram_range (1,2) should yield at least one bigram.
    assert any(" " in tok for tok in vec.get_feature_names_out())


# --- Deterministic, leakage-free split ---------------------------------------
@requires_data
@pytest.mark.parametrize(
    "task,classes",
    [("type", TYPE_CLASSES), ("severity", SEVERITY_CLASSES)],
)
def test_split_deterministic_and_leakage_free(task, classes):
    if task == "severity" and not SEVERITY_DATA_READY:
        pytest.skip("severity dataset absent (opt-in, not shipped)")
    split = make_split(task)

    # Disjoint by ROW INDEX -> the three partitions share no rows. (The `id`
    # column is the per-repo issue number and is NOT globally unique, so it
    # cannot serve as a row identity; the DataFrame index can.)
    idx_train = set(split.X_train.index)
    idx_val = set(split.X_val.index)
    idx_test = set(split.X_test.index)
    assert idx_train.isdisjoint(idx_val)
    assert idx_train.isdisjoint(idx_test)
    assert idx_val.isdisjoint(idx_test)

    # Disjoint by TEXT -> the real leakage that matters: no identical issue text
    # appears in more than one partition (load_task_frame dedupes exact texts).
    txt_train = set(split.X_train)
    txt_val = set(split.X_val)
    txt_test = set(split.X_test)
    assert txt_train.isdisjoint(txt_val)
    assert txt_train.isdisjoint(txt_test)
    assert txt_val.isdisjoint(txt_test)

    # Class set preserved across the full split and the declared class list.
    all_labels = set(split.y_train) | set(split.y_val) | set(split.y_test)
    assert all_labels == set(classes)
    assert set(split.classes) == set(classes)


@requires_data
def test_split_is_reproducible():
    a = make_split("type")
    b = make_split("type")
    assert list(a.ids_train) == list(b.ids_train)
    assert list(a.ids_test) == list(b.ids_test)


# --- Production inference schema (torch-free) ---------------------------------
def test_predict_triage_schema():
    from agenclave.classifier.predict import ModelsNotTrained, predict_triage

    try:
        result = predict_triage(
            "App crashes on launch", "Stack trace shows a null pointer exception"
        )
    except ModelsNotTrained as exc:
        pytest.skip(f"production models not trained: {exc}")

    assert set(result) == {
        "label",
        "label_confidence",
        "severity",
        "severity_confidence",
        "top_tokens",
    }
    assert result["label"] in TYPE_CLASSES
    assert 0.0 <= result["label_confidence"] <= 1.0
    assert isinstance(result["top_tokens"], list)
    assert all(isinstance(tok, str) for tok in result["top_tokens"])
    # Severity optional (type-only deliverable): valid class + [0,1] conf, or None.
    if result["severity"] is None:
        assert result["severity_confidence"] is None
    else:
        assert result["severity"] in SEVERITY_CLASSES
        assert 0.0 <= result["severity_confidence"] <= 1.0


def test_predict_module_is_torch_free():
    # The serving import path must not pull in torch / sentence-transformers.
    # Importing predict should not import torch.
    import agenclave.classifier.predict  # noqa: F401

    assert "torch" not in sys.modules, "predict.py must stay torch-free"


# --- MiniLM embedding path: guarded so tests stay fast (no model download) ----
@pytest.mark.skip(reason="MiniLM embedding test skipped to avoid model download")
def test_minilm_embedder_smoke():  # pragma: no cover - intentionally skipped
    from agenclave.classifier.features import MiniLMEmbedder

    emb = MiniLMEmbedder().transform(["hello world", "another issue"])
    assert emb.shape[0] == 2
    assert emb.shape[1] > 0
