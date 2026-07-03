# Datasets, provenance & licenses

> Filled in by the data step. **No fabricated data.** Exact source URLs,
> licenses, and (expected) row counts are recorded here. Counts marked
> "expected (pending run)" are derived from the published source statistics; the
> actual download + normalization is produced by `scripts/prepare_data.py`
> (deterministic, seed=42). Raw files cache under `data/raw/` (gitignored);
> canonical CSVs are written to `data/processed/` (gitignored).

## Issue-type classification (Stage 1), `data/processed/issues.csv`

- **Source:** NLBSE'23 Tool Competition on Issue Report Classification.
  - Repo: https://github.com/nlbse2023/issue-report-classification
  - Train: https://tickettagger.blob.core.windows.net/datasets/nlbse23-issue-classification-train.csv.tar.gz (~514 MB, verified HTTP 200)
  - Test:  https://tickettagger.blob.core.windows.net/datasets/nlbse23-issue-classification-test.csv.tar.gz (~57 MB, verified HTTP 200)
- **License:** AGPL-3.0 (per NLBSE'23 repo). Used here for research / a
  non-commercial portfolio project, with attribution.
- **Raw schema:** CSV columns `label, id, title, body, author_association`.
- **Raw size:** ~1,275,881 train rows, ~142,320 test rows. Heavily skewed:
  bug 52.6% / feature 37% / question 6% / documentation 4.4%. Large + skewed,
  so we **stratified-subsample** (seed=42).
- **Canonical labels** (exact): `bug`, `feature_request`, `documentation`,
  `question_other`. Mapping: bug→bug, feature→feature_request,
  documentation→documentation, question→question_other. (`performance` is
  intentionally absent, no gold labels exist; documented integrity choice.)
- **Canonical CSV:** `issues.csv` with columns `id, title, body, label`.
- **Expected per-class rows (pending run):** up to ~3,000 per class via
  stratified subsample (`--per-class`, default 3000). `documentation` is the
  scarcest class but has >56k raw rows, so all four classes hit the target →
  ~3,000 × 4 ≈ **12,000 rows, balanced**. Actual counts printed at run time.
- **Split:** the classifier step performs its own stratified train/val/test
  split with a fixed seed (no leakage).

## Severity (Stage 1, second head), ⛔ OMITTED from the shipped deliverable

> **Decision (2026-06-16):** the severity head is **not shipped**. No cleanly
> OSS/SPDX-licensed, directly-downloadable severity source at usable size was
> found; the only well-formed option is citation-only (details below). Rather
> than ship a deliverable built on an unlicensed source or fabricate labels,
> Agenclave ships **type-only** and documents severity as a deliberate
> integrity omission. The data path below is preserved for **local-only**
> experimentation behind an explicit opt-in
> (`python scripts/prepare_data.py --with-severity`); its output is never part
> of the shipped model or results.

### (Opt-in only) `data/processed/severity.csv`

- **Source:** `AliArshad/Bugzilla_Eclipse_Bug_Reports_Dataset` (HuggingFace),
  a processed slice of the canonical **Lamkanfi / Perez / Demeyer** Eclipse &
  Mozilla defect tracking dataset (MSR'13).
  - HF dataset: https://huggingface.co/datasets/AliArshad/Bugzilla_Eclipse_Bug_Reports_Dataset (verified resolvable, HTTP 200)
  - Loadable via `datasets.load_dataset("AliArshad/Bugzilla_Eclipse_Bug_Reports_Dataset")`.
  - Underlying dataset: Lamkanfi et al., "The Eclipse and Mozilla defect
    tracking dataset", MSR'13, Zenodo DOI 10.5281/zenodo.268443,
    GitHub `ansymo/msr2013-bug_dataset`.
- **License:** ⚠️ **No explicit OSS/SPDX license.** The HF card carries only a
  citation request; the underlying MSR'13 dataset is "publicly available for
  research, please cite the paper." It is **not** formally EPL-2.0/permissive.
  Treated here as a citable academic dataset for a non-commercial portfolio,
  with full attribution. (The originally-scoped Mendeley "Dataset on Eclipse
  Bug Records on Bugzilla", EPL-2.0, has no stable unauthenticated direct-file
  download URL; the Zenodo `Eclipse_dataset.zip` is 17.2 GB with only a
  100-row `sample_data.csv`, both rejected as not cleanly fetchable at usable
  size. See "Severity source notes" below.)
- **Raw schema:** CSV columns `Project, Bug ID, Severity Label,
  Resolution Status, Short Description`. 88,682 rows (all `Resolution=FIXED`),
  no separate body field, so `body` is left empty and `Short Description`
  populates `title`.
- **Raw `Severity Label` counts:** normal 72,170; critical 5,936; major 4,573;
  minor 3,125; trivial 2,080; blocker 798. No `enhancement` rows present.
- **Canonical labels** (exact): `low`, `medium`, `high`. Mapping:
  blocker/critical/major→`high` (11,307 raw), normal→`medium` (72,170 raw),
  minor/trivial→`low` (5,205 raw). Non-defect rows (enhancement/feature/etc.)
  dropped if present.
- **Canonical CSV:** `severity.csv` with columns `id, title, body, severity`.
- **Expected per-class rows (pending run):** stratified subsample up to ~3,000
  per class. `low` has 5,205 and `high` 11,307 raw → all three classes hit
  ~3,000 → ~3,000 × 3 ≈ **9,000 rows, balanced**. Actual counts printed at run
  time.

### Severity source notes (why it's omitted)
A cleanly EPL-2.0-licensed, directly-downloadable severity CSV at usable size
was **not** found. The HF source above is directly downloadable and well-formed
but is licensed only as a citable research dataset (no SPDX license). Because the
shipped deliverable must rest on a properly licensed source, and fabrication is
forbidden, severity is **omitted from the deliverable** (decision 2026-06-16).
The path remains available for local experimentation only via
`python scripts/prepare_data.py --with-severity`; nothing it produces is shipped.

## Code-fix verification (trust harness)

- **Source:** self-contained fixtures that ship with the repo, each carrying its
  own runnable tests (`tests/fixtures/`, plus the task library in
  `scripts/verified_run.py`). No external dataset is downloaded.
- **Why in-repo:** the trust signal comes from running each candidate patch against
  a task's OWN tests in-loop, so keeping the fixtures in the repo makes verification
  deterministic and keeps per-model reliability strictly separate from any held-out
  grade.

## Reproduce

```bash
python scripts/prepare_data.py                 # type head only (default; shipped)
python scripts/prepare_data.py --force         # refresh raw caches
python scripts/prepare_data.py --per-class 3000
python scripts/prepare_data.py --with-severity # opt-in severity (local only; NOT shipped)
```

The default run downloads only the ~57 MB NLBSE'23 test partition as the sample
pool (use `--full-pool` for the ~514 MB train file). The script is deterministic
(seed=42), idempotent (skips re-download if the raw cache exists), prints
resulting per-class counts, and fails loudly if a source is unreachable (never
substitutes fabricated data).
