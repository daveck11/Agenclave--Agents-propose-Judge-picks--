#!/usr/bin/env python3
# Prepare canonical datasets for Agenclave Stage 1 (issue-type head; shipped).
#
# This script downloads two real, citable, directly-downloadable sources, caches
# the raw files under `data/raw/` (gitignored), and writes normalized CSVs to
# `data/processed/`. Nothing is synthesised. If a source is unreachable the
# script fails loudly; it never silently substitutes fake data.
#
# Sources
# -------
# 1. Issue-type classification (-> data/processed/issues.csv)
#    NLBSE'23 Tool Competition on Issue Report Classification.
#    Repo:    https://github.com/nlbse2023/issue-report-classification
#    Files:   https://tickettagger.blob.core.windows.net/datasets/
#               nlbse23-issue-classification-train.csv.tar.gz  (~514 MB)
#               nlbse23-issue-classification-test.csv.tar.gz   (~57 MB)
#    License: AGPL-3.0 (see NLBSE'23 repo). Used here for research/portfolio.
#    Schema:  CSV with columns: label, id (repo issue id), title, body,
#             author_association. ~1.27M train rows, heavily skewed
#             (bug 52.6% / feature 37% / question 6% / documentation 4.4%).
#    Label mapping to canonical {bug, feature_request, documentation,
#             question_other}:
#               bug           -> bug
#               feature       -> feature_request
#               documentation -> documentation
#               question      -> question_other
#    Because the full set is large and skewed, we stratified-subsample to a
#    documented per-class target (deterministic, seed=42) and print counts.
#
# 2. Bug severity (-> data/processed/severity.csv)
#    HuggingFace mirror "AliArshad/Bugzilla_Eclipse_Bug_Reports_Dataset", a
#    processed slice of the canonical Lamkanfi/Perez/Demeyer Eclipse & Mozilla
#    defect tracking dataset (MSR'13).
#    HF id:   AliArshad/Bugzilla_Eclipse_Bug_Reports_Dataset
#    File:    "filtered_data.xlsx - Sheet1.csv" (~7.7 MB, 88,682 rows)
#    Columns: Project, Bug ID, Severity Label, Resolution Status,
#             Short Description.
#    License: NOT an explicit OSS license. The underlying MSR'13 dataset is
#             publicly available "for research, please cite the paper"
#             (Lamkanfi et al., 2013; Zenodo DOI 10.5281/zenodo.268443). Treated
#             here as a citable academic dataset for a non-commercial portfolio.
#    Severity Label distinct values & counts (full set):
#             normal 72170, critical 5936, major 4573, minor 3125,
#             trivial 2080, blocker 798.
#    Mapping to canonical {low, medium, high}:
#               blocker, critical, major -> high   (11,307 rows)
#               normal                   -> medium (72,170 rows)
#               minor, trivial           -> low    ( 5,205 rows)
#    "enhancement"/non-defect rows are dropped (none present in this slice).
#    This source has no separate body field; `body` is left empty and the
#    Short Description populates `title`.
#
# Outputs (canonical CSVs)
# ------------------------
# - data/processed/issues.csv   : id, title, body, label
#       label   in {bug, feature_request, documentation, question_other}
# - data/processed/severity.csv : id, title, body, severity
#       severity in {low, medium, high}
#
# Determinism / idempotency
# -------------------------
# - Fixed seed (42) for all subsampling.
# - Raw downloads are cached under data/raw/; re-runs skip download unless
#   --force is given.
# - Prints resulting per-class counts for both CSVs.
#
# Only the type head ships. I dropped the severity head because I couldn't
# find a cleanly licensed severity source at usable size (the HF mirror is
# citation-only, no formal license). The severity path below is kept for
# local experiments behind an opt-in flag, but it isn't part of the app.
#
# Usage
# -----
#     python scripts/prepare_data.py                 # type head only (default; shipped)
#     python scripts/prepare_data.py --force         # re-download raw caches
#     python scripts/prepare_data.py --per-class 3000
#     python scripts/prepare_data.py --with-severity # opt-in, not shipped (see above)
#
# Only uses libraries already pinned in requirements.txt (pandas, datasets,
# huggingface-hub) plus the Python stdlib (urllib, tarfile).

from __future__ import annotations

import argparse
import sys
import tarfile
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

# --- Repo-root-relative paths (mirror src/agenclave/config.py so this script
#     works from any CWD without importing the package / pulling pydantic). ---
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

SEED = 42

# --- NLBSE'23 issue report classification -------------------------------------
NLBSE_BASE = "https://tickettagger.blob.core.windows.net/datasets"
NLBSE_TRAIN_URL = f"{NLBSE_BASE}/nlbse23-issue-classification-train.csv.tar.gz"
NLBSE_TEST_URL = f"{NLBSE_BASE}/nlbse23-issue-classification-test.csv.tar.gz"
NLBSE_TRAIN_TGZ = RAW_DIR / "nlbse23-train.csv.tar.gz"
NLBSE_TEST_TGZ = RAW_DIR / "nlbse23-test.csv.tar.gz"

# NLBSE label -> canonical issue label.
TYPE_LABEL_MAP = {
    "bug": "bug",
    "feature": "feature_request",
    "documentation": "documentation",
    "question": "question_other",
}
TYPE_CLASSES = ["bug", "feature_request", "documentation", "question_other"]

# --- Bugzilla/Eclipse severity (HuggingFace mirror of Lamkanfi MSR'13) ---------
SEVERITY_HF_ID = "AliArshad/Bugzilla_Eclipse_Bug_Reports_Dataset"

# Raw Bugzilla severity -> canonical severity.
SEVERITY_MAP = {
    "blocker": "high",
    "critical": "high",
    "major": "high",
    "normal": "medium",
    "minor": "low",
    "trivial": "low",
}
SEVERITY_CLASSES = ["low", "medium", "high"]
# Values that are not real defects and must be dropped if present.
SEVERITY_DROP = {"enhancement", "feature", "task", "n/a", "", "none"}

# Default per-class subsample target (rows kept per class where the source has
# enough). Aim ~2,000-4,000 per class, classes reasonably balanced.
DEFAULT_PER_CLASS = 3000


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def _die(msg: str) -> "None":
    print(f"\nERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def _download(url: str, dest: Path, force: bool) -> Path:
    # Download `url` to `dest` with caching. Fails loudly on error.
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        print(f"  [cache] {dest.name} ({dest.stat().st_size:,} bytes) - skipping download")
        return dest
    print(f"  [get]   {url}")
    print(f"          -> {dest}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "agenclave-prepare/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 (trusted hosts)
            tmp = dest.with_suffix(dest.suffix + ".part")
            with open(tmp, "wb") as fh:
                while True:
                    chunk = resp.read(1 << 20)  # 1 MiB
                    if not chunk:
                        break
                    fh.write(chunk)
            tmp.replace(dest)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        _die(
            f"failed to download {url}\n  reason: {exc}\n"
            "  The source must be reachable; there is no synthetic fallback."
        )
    print(f"  [done]  {dest.name} ({dest.stat().st_size:,} bytes)")
    return dest


def _read_tar_csv(tgz_path: Path) -> pd.DataFrame:
    # Read the single CSV inside a .tar.gz into a DataFrame.
    try:
        with tarfile.open(tgz_path, "r:gz") as tar:
            members = [m for m in tar.getmembers() if m.name.lower().endswith(".csv")]
            if not members:
                _die(f"no CSV found inside {tgz_path.name}")
            member = members[0]
            fh = tar.extractfile(member)
            if fh is None:
                _die(f"could not extract {member.name} from {tgz_path.name}")
            return pd.read_csv(fh)
    except (tarfile.TarError, OSError) as exc:
        _die(f"failed to read archive {tgz_path.name}: {exc}")


def _stratified_sample(df: pd.DataFrame, label_col: str, per_class: int) -> pd.DataFrame:
    # Keep up to `per_class` rows per label (deterministic, seed=SEED).
    parts = []
    for label, grp in df.groupby(label_col, sort=True):
        n = min(per_class, len(grp))
        parts.append(grp.sample(n=n, random_state=SEED))
    out = pd.concat(parts, ignore_index=True)
    return out.sample(frac=1.0, random_state=SEED).reset_index(drop=True)


def _print_counts(df: pd.DataFrame, col: str, title: str) -> None:
    print(f"\n  {title} per-class counts:")
    counts = df[col].value_counts().sort_index()
    for label, n in counts.items():
        print(f"    {label:<16} {n:>7,}")
    print(f"    {'TOTAL':<16} {len(df):>7,}")


# ------------------------------------------------------------------------------
# Issue-type head
# ------------------------------------------------------------------------------
def prepare_issues(per_class: int, force: bool, full_pool: bool = False) -> None:
    print("\n=== Issue-type classification (NLBSE'23) ===")
    # We draw a small balanced subsample (~per_class/class) and then perform our
    # OWN stratified train/val/test split downstream, so NLBSE's train/test split
    # semantics are irrelevant here. By default we pull from the published *test*
    # partition (~57 MB, ~142k rows) rather than the ~514 MB / ~1.27M-row train
    # file: same class distribution, far cheaper to download and read. Pass
    # --full-pool to use the large train file instead.
    if full_pool:
        pool_tgz = _download(NLBSE_TRAIN_URL, NLBSE_TRAIN_TGZ, force)
        print("  reading train archive (this can take a moment; ~1.27M rows)...")
    else:
        pool_tgz = _download(NLBSE_TEST_URL, NLBSE_TEST_TGZ, force)
        print("  reading NLBSE'23 test partition (~142k rows) as the sample pool...")
    df = _read_tar_csv(pool_tgz)

    # Normalize column names defensively. NLBSE'23 headers are
    # `id, labels, title, body, author_association` (the label column is
    # singular-valued but named "labels"); older dumps use "label".
    cols = {c.lower().strip(): c for c in df.columns}
    label_col = cols.get("label") or cols.get("labels")
    if not label_col:
        _die(f"no label column found in NLBSE CSV; got {list(df.columns)}")
    for r in ("title", "body"):
        if r not in cols:
            _die(f"expected column '{r}' not found in NLBSE CSV; got {list(df.columns)}")
    id_col = cols.get("id")

    df = df.rename(columns={label_col: "label", cols["title"]: "title", cols["body"]: "body"})
    if id_col:
        df = df.rename(columns={id_col: "id"})
    else:
        df["id"] = range(len(df))

    df["label"] = df["label"].astype(str).str.strip().str.lower()
    df = df[df["label"].isin(TYPE_LABEL_MAP)].copy()
    df["label"] = df["label"].map(TYPE_LABEL_MAP)

    df["title"] = df["title"].fillna("").astype(str)
    df["body"] = df["body"].fillna("").astype(str)
    # Drop rows with no usable text.
    df = df[(df["title"].str.strip() != "") | (df["body"].str.strip() != "")]

    out = _stratified_sample(df, "label", per_class)
    out = out[["id", "title", "body", "label"]]

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    dest = PROCESSED_DIR / "issues.csv"
    out.to_csv(dest, index=False)
    print(f"\n  wrote {dest} ({len(out):,} rows)")
    _print_counts(out, "label", "issues.csv")


# ------------------------------------------------------------------------------
# Severity head
# ------------------------------------------------------------------------------
def prepare_severity(per_class: int, force: bool) -> None:
    print("\n=== Bug severity (Bugzilla/Eclipse, Lamkanfi MSR'13 via HF) ===")
    # Download the single CSV file directly via huggingface_hub into the default
    # (short-path) HF cache. We avoid `datasets.load_dataset` with a deep custom
    # cache_dir because, on Windows, it builds a lock filename encoding the full
    # cache path that overflows MAX_PATH (260). Fail loudly on any error.
    try:
        from huggingface_hub import hf_hub_download, list_repo_files
    except ImportError:
        _die("`huggingface_hub` is required (pinned in requirements.txt).")

    print(f"  resolving CSV file in HF dataset '{SEVERITY_HF_ID}'")
    try:
        files = list_repo_files(SEVERITY_HF_ID, repo_type="dataset")
        csv_files = [f for f in files if f.lower().endswith(".csv")]
        if not csv_files:
            _die(f"no CSV file in HF dataset '{SEVERITY_HF_ID}'; files: {files}")
        csv_name = csv_files[0]
        print(f"  [get]   {csv_name}")
        local = hf_hub_download(
            SEVERITY_HF_ID, filename=csv_name, repo_type="dataset", force_download=force
        )
        print(f"  [done]  cached at {local}")
        df = pd.read_csv(local)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - surface any load error loudly
        _die(
            f"failed to load HF severity dataset '{SEVERITY_HF_ID}': {exc}\n"
            "  The source must be reachable; there is no synthetic fallback."
        )

    # Expected columns: Project, Bug ID, Severity Label, Resolution Status,
    # Short Description.
    cols = {c.lower().strip(): c for c in df.columns}
    sev_col = cols.get("severity label") or cols.get("severity")
    desc_col = cols.get("short description") or cols.get("summary") or cols.get("title")
    id_col = cols.get("bug id") or cols.get("id")
    if not sev_col or not desc_col:
        _die(
            "severity source schema changed; expected 'Severity Label' and "
            f"'Short Description'. Got: {list(df.columns)}"
        )

    df = df.rename(columns={sev_col: "severity_raw", desc_col: "title"})
    df["id"] = df[id_col] if id_col else range(len(df))

    df["severity_raw"] = df["severity_raw"].astype(str).str.strip().str.lower()
    df = df[~df["severity_raw"].isin(SEVERITY_DROP)]
    df = df[df["severity_raw"].isin(SEVERITY_MAP)].copy()
    df["severity"] = df["severity_raw"].map(SEVERITY_MAP)

    df["title"] = df["title"].fillna("").astype(str)
    df["body"] = ""  # this source has no separate body field
    df = df[df["title"].str.strip() != ""]

    out = _stratified_sample(df, "severity", per_class)
    out = out[["id", "title", "body", "severity"]]

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    dest = PROCESSED_DIR / "severity.csv"
    out.to_csv(dest, index=False)
    print(f"\n  wrote {dest} ({len(out):,} rows)")
    _print_counts(out, "severity", "severity.csv")


# ------------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare canonical datasets for Agenclave Stage 1 (issue-type head; shipped).")
    parser.add_argument(
        "--force", action="store_true", help="re-download raw caches"
    )
    parser.add_argument(
        "--with-severity",
        action="store_true",
        help="ALSO prepare the severity head (opt-in; NOT part of the shipped "
        "deliverable - the source is citation-only, not OSS-licensed). Default "
        "is type-only.",
    )
    parser.add_argument(
        "--per-class",
        type=int,
        default=DEFAULT_PER_CLASS,
        help=f"max rows kept per class when subsampling (default {DEFAULT_PER_CLASS})",
    )
    parser.add_argument(
        "--full-pool",
        action="store_true",
        help="draw the issue subsample from the large ~514 MB train file instead "
        "of the lighter ~57 MB test partition (same distribution either way)",
    )
    args = parser.parse_args()

    print(f"Agenclave data prep | root={ROOT}")
    print(f"  raw cache:  {RAW_DIR}")
    print(f"  processed:  {PROCESSED_DIR}")
    print(f"  seed={SEED}  per_class={args.per_class}")

    prepare_issues(args.per_class, args.force, full_pool=args.full_pool)

    if args.with_severity:
        print(
            "\n=== --with-severity: preparing severity head (OPT-IN). ===\n"
            "    NOTE: this source is citation-only (not OSS/SPDX-licensed) and is\n"
            "    NOT part of the shipped Agenclave deliverable. For local use only."
        )
        prepare_severity(args.per_class, args.force)
    else:
        print(
            "\n=== Severity head omitted (default): type head only. ===\n"
            "    No cleanly licensed severity source was found.\n"
            "    Pass --with-severity for local-only experimentation."
        )

    print("\nDone.")


if __name__ == "__main__":
    main()
