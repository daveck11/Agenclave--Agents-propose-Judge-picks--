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
