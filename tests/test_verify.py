# verify_patch should detect each trust tier on the calc_bug fixture.
# No network; each candidate is applied to a sandbox copy and tested.

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agenclave.harness.verify import verify_patch  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "calc_bug"
REPO = FIX / "repo"
TEST_CMD = [sys.executable, "-m", "pytest", "check_add.py", "-q"]


def _patch(name: str) -> str:
    return (FIX / "patches" / name).read_text(encoding="utf-8")


def test_correct_patch_applies_and_passes():
    r = verify_patch(_patch("correct.diff"), REPO, TEST_CMD)
    assert r.applies
    assert r.tests_passed
    assert r.passed == 2


def test_wrong_patch_applies_but_fails():
    r = verify_patch(_patch("wrong.diff"), REPO, TEST_CMD)
    assert r.applies
    assert not r.tests_passed


def test_broken_patch_does_not_apply():
    r = verify_patch(_patch("broken.diff"), REPO, TEST_CMD)
    assert not r.applies
    assert not r.tests_passed


def test_empty_patch_is_error():
    r = verify_patch("", REPO, TEST_CMD)
    assert not r.applies
    assert r.error


def test_malformed_hunk_header_still_applies_by_content():
    # A correct fix a model emitted with a bare "@@" header (no line numbers) and
    # no ---/+++ lines: git apply rejects it, but the content-match fallback
    # recovers it so a right answer isn't thrown away on formatting.
    patch = (
        "diff --git a/calc.py b/calc.py\n"
        "@@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
    )
    r = verify_patch(patch, REPO, TEST_CMD)
    assert r.applies
    assert r.tests_passed


def test_content_fallback_does_not_rescue_a_wrong_fix():
    # A malformed-header patch whose content does not match the file must NOT be
    # force-applied (no false positives from the fallback).
    patch = (
        "diff --git a/calc.py b/calc.py\n"
        "@@\n"
        " def add(a, b):\n"
        "-    return a * b\n"  # this line is not in the file
        "+    return a + b\n"
    )
    r = verify_patch(patch, REPO, TEST_CMD)
    assert not r.applies
