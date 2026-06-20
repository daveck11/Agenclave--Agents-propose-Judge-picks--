# Model Card, Agenclave triage classifier

> Filled in after training with **real** metrics. Placeholder sections below.

## Intended use
Triage incoming software issue reports into a coarse **issue type** to (a)
route/filter and (b) annotate tasks for the Stage 2 code-fix harness. Not a
substitute for human triage on high-stakes decisions.

**Scope:** the shipped model is **type-only**, classes `{bug, feature_request,
documentation, question_other}` (NLBSE'23). A severity head was scoped but is
**omitted from the deliverable**: no cleanly OSS/SPDX-licensed, fetchable
severity source was found (only a citation-only one), and labels are never
fabricated. The severity head can be trained locally for experimentation via
`scripts/prepare_data.py --with-severity` + `scripts/train_classifier.py
--with-severity`, but its output is not part of this card or the shipped model.

## Model
- Features compared: **TF-IDF** (word 1-2 grams, sublinear tf, English stop-words,
  vocab ≤ 50k) vs **sentence-transformer embeddings** (`all-MiniLM-L6-v2`, CPU).
- Estimators: Logistic Regression, Random Forest (4 configs total).
- Selection: best **validation** macro-F1 → **TF-IDF + Logistic Regression**, which
  is also the served production model (torch-free + interpretable top tokens).

## Training data
See [`../data/README.md`](../data/README.md). 11,947 issues after exact-text
dedup (4 balanced classes), stratified **70/15/15** train/val/test, seed=42.
Dedup happens **before** splitting and the split is asserted leakage-free
(disjoint by row index *and* by text) in `tests/test_features.py`.

## Metrics (held-out test set, n = 1,793)
Served model, **TF-IDF + Logistic Regression**: macro-F1 **0.675**, accuracy **0.674**.

Per-class (served model):

| class            | precision | recall | f1    | support |
| ---------------- | --------- | ------ | ----- | ------- |
| bug              | 0.654     | 0.690  | 0.672 | 449     |
| feature_request  | 0.660     | 0.696  | 0.678 | 448     |
| documentation    | 0.773     | 0.686  | 0.727 | 446     |
| question_other   | 0.624     | 0.624  | 0.624 | 450     |

Transformer-lift comparison (test macro-F1 / accuracy):

| config                | macro-F1 | accuracy |
| --------------------- | -------- | -------- |
| **tfidf + logreg** ✅ | **0.675**| 0.674    |
| tfidf + randomforest  | 0.653    | 0.655    |
| minilm + logreg       | 0.628    | 0.628    |
| minilm + randomforest | 0.569    | 0.578    |

**Honest finding, no transformer lift here.** The best MiniLM config (0.628)
*underperforms* the best TF-IDF config (0.675); lift = **−0.047**. On short issue
text with a focused vocabulary, a linear TF-IDF model is both stronger and
lighter, so the served model is also the most interpretable and torch-free.
`documentation` is the easiest class (f1 0.73); the `question_other` catch-all is
the hardest (f1 0.62), most often confused with `bug`. Confusion matrix:
[`../results/cm_type.png`](../results/cm_type.png); full numbers:
[`../results/classifier_metrics.json`](../results/classifier_metrics.json).

## Limitations
- Label taxonomy is coarse and dataset-dependent (see data README).
- Trained on open-source GitHub issues; may not transfer to other domains.
- No `performance` class and no severity head (both deliberate, documented
  omissions, no gold labels / no cleanly licensed source; never fabricated).
- If the optional severity head is trained, severity is inherently
  noisy/subjective; treat it as a hint, not ground truth.

## Ethical / honesty notes
Real metrics only. Failure modes and class imbalance are reported, not hidden.
