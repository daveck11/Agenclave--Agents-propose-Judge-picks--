# Feature pipelines for the triage classifier.
#
# Two feature families, compared for the "transformer lift":
#
# 1. `make_tfidf_vectorizer`, a word n-gram (1-2) TF-IDF vectorizer with
#    sublinear tf. This is the *production* feature path: interpretable (vocab x
#    linear coefficients give top tokens) and torch-free, so the API can serve
#    without sentence-transformers / torch.
#
# 2. `MiniLMEmbedder`, a sklearn-compatible transformer wrapping
#    sentence-transformers `all-MiniLM-L6-v2`. Used only to measure the lift in
#    training/evaluation; it is NOT persisted for serving (heavy runtime dep).
#
# `MiniLMEmbedder` imports sentence-transformers *lazily* inside `transform`
# so that importing this module (e.g. from the torch-free serving path) does not
# pull in torch.

from __future__ import annotations

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.feature_extraction.text import TfidfVectorizer

MINILM_MODEL_NAME = "all-MiniLM-L6-v2"


def make_tfidf_vectorizer(
    *,
    ngram_range: tuple[int, int] = (1, 2),
    min_df: int = 2,
    max_features: int = 50_000,
    sublinear_tf: bool = True,
) -> TfidfVectorizer:
    # Word 1-2 grams, min_df to drop rare noise, capped vocab. Sublinear tf
    # helps because issue text is bursty (the same token repeated in a
    # stack trace shouldn't dominate).
    return TfidfVectorizer(
        lowercase=True,
        stop_words="english",
        ngram_range=ngram_range,
        min_df=min_df,
        max_features=max_features,
        sublinear_tf=sublinear_tf,
        strip_accents="unicode",
    )


class MiniLMEmbedder(BaseEstimator, TransformerMixin):
    # sklearn transformer: text -> MiniLM sentence embeddings. Only used for
    # the embeddings-vs-tfidf comparison in training; the served pipeline
    # never loads this (it lost, see the results table).

    # Process-wide cache so multiple configs in one run share one model load.
    _MODEL_CACHE: dict = {}

    def __init__(
        self,
        model_name: str = MINILM_MODEL_NAME,
        batch_size: int = 64,
        normalize: bool = True,
    ) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self.normalize = normalize

    def _get_model(self):
        model = MiniLMEmbedder._MODEL_CACHE.get(self.model_name)
        if model is None:
            # Lazy import: keeps torch out of the serving import path.
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(self.model_name, device="cpu")
            MiniLMEmbedder._MODEL_CACHE[self.model_name] = model
        return model

    def fit(self, X, y=None):  # noqa: D401 - stateless (embeddings are fixed)
        return self

    def transform(self, X) -> np.ndarray:
        texts = [("" if t is None else str(t)) for t in X]
        model = self._get_model()
        emb = model.encode(
            texts,
            batch_size=self.batch_size,
            convert_to_numpy=True,
            normalize_embeddings=self.normalize,
            show_progress_bar=False,
        )
        return np.asarray(emb, dtype=np.float32)
