# Curated practice bugs ("fixtures") for the demo and the verified reliability
# harness. Each fixture is a tiny self-contained repo (one buggy module) plus a
# check_*.py test that decides whether a candidate patch actually fixes it.
#
# One registry, two consumers:
#   - the web app lists these so a user can load a practice bug into the pipeline
#     (Stage 1 triage -> Stage 2 code-fix) without wiring up a real codebase;
#   - scripts/verified_run.py dispatches each to the agents and verifies patches
#     against the tests to build per-model reliability.
#
# This stands in for a real codebase connection: in production the file and its
# tests come from the user's repo; here they ship with the demo so the whole
# loop (dispatch -> apply -> run tests -> rank) is reproducible offline.

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = ROOT / "tests" / "fixtures"


@dataclass(frozen=True)
class Fixture:
    id: str          # stable kebab-case id
    title: str       # issue-style one-liner (feeds Stage 1 triage)
    body: str        # issue description; doubles as the agent problem statement
    category: str    # triage label; every fixture here is a bug
    dir_name: str    # folder under tests/fixtures/
    module: str      # the buggy file, e.g. "calc.py"
    test: str        # the check_*.py test file that verifies a fix

    @property
    def repo(self) -> Path:
        return FIXTURES_DIR / self.dir_name / "repo"

    @property
    def test_cmd(self) -> list[str]:
        # verify_patch runs this inside a throwaway copy of `repo`.
        return [sys.executable, "-m", "pytest", self.test, "-q"]

    def buggy_code(self) -> str:
        # The current (broken) file contents, for showing the code in the demo.
        return (self.repo / self.module).read_text(encoding="utf-8")


FIXTURES: list[Fixture] = [
    Fixture(
        id="calc-add",
        title="add() returns the wrong result",
        body=(
            "The add(a, b) function in calc.py returns a - b instead of a + b, so "
            "addition is actually doing subtraction. Fix it so add returns the sum."
        ),
        category="bug",
        dir_name="calc_bug",
        module="calc.py",
        test="check_add.py",
    ),
    Fixture(
        id="last-n-off-by-one",
        title="last_n() is off by one",
        body=(
            "last_n(items, n) in seq.py should return the last n items of the "
            "sequence, but it returns n-1 items (an off-by-one error). Fix it so it "
            "returns exactly the last n items."
        ),
        category="bug",
        dir_name="off_by_one",
        module="seq.py",
        test="check_seq.py",
    ),
    Fixture(
        id="mutable-default",
        title="collect() shares state between calls",
        body=(
            "collect(value, into=[]) in acc.py uses a mutable default argument, so the "
            "same list is reused across calls and results leak between them. A call "
            "with no bucket should start from a fresh empty list. Fix the mutable "
            "default."
        ),
        category="bug",
        dir_name="mutable_default",
        module="acc.py",
        test="check_acc.py",
    ),
    Fixture(
        id="factorial-base",
        title="factorial(0) recurses forever",
        body=(
            "factorial(n) in mathx.py only treats n == 1 as a base case, so "
            "factorial(0) recurses infinitely and eventually errors. factorial(0) "
            "should return 1. Add the missing base case."
        ),
        category="bug",
        dir_name="recursion",
        module="mathx.py",
        test="check_mathx.py",
    ),
    Fixture(
        id="fizzbuzz-order",
        title="FizzBuzz prints 'Fizz' for multiples of 15",
        body=(
            "fizzbuzz(n) in fizzbuzz.py checks n % 3 and n % 5 before n % 15, so "
            "multiples of 15 return 'Fizz' instead of 'FizzBuzz'. Reorder the checks "
            "so 15, 30, ... return 'FizzBuzz'."
        ),
        category="bug",
        dir_name="fizzbuzz",
        module="fizzbuzz.py",
        test="check_fizzbuzz.py",
    ),
    Fixture(
        id="average-empty",
        title="mean() crashes on an empty list",
        body=(
            "mean(numbers) in stats.py divides by len(numbers) with no guard, so "
            "mean([]) raises ZeroDivisionError. An empty list should return 0 instead "
            "of crashing."
        ),
        category="bug",
        dir_name="average",
        module="stats.py",
        test="check_stats.py",
    ),
    Fixture(
        id="palindrome-case",
        title="is_palindrome() is case-sensitive",
        body=(
            "is_palindrome(s) in text.py compares the string to its reverse directly, "
            "so 'Racecar' is reported as not a palindrome. It should ignore case, so "
            "'Racecar' counts as a palindrome."
        ),
        category="bug",
        dir_name="palindrome",
        module="text.py",
        test="check_text.py",
    ),
    Fixture(
        id="dedupe-order",
        title="unique() does not preserve order",
        body=(
            "unique(items) in sequtil.py builds a set, which loses the original order. "
            "It should remove duplicates while keeping the first-seen order of the "
            "remaining items."
        ),
        category="bug",
        dir_name="dedupe",
        module="sequtil.py",
        test="check_sequtil.py",
    ),
    Fixture(
        id="celsius-to-fahrenheit",
        title="Celsius to Fahrenheit is missing the +32",
        body=(
            "c_to_f(celsius) in convert.py returns celsius * 9 / 5 but forgets to add "
            "32, so 0C returns 0 instead of 32. Fix the formula to "
            "(celsius * 9 / 5) + 32."
        ),
        category="bug",
        dir_name="temperature",
        module="convert.py",
        test="check_convert.py",
    ),
    Fixture(
        id="clamp-bounds",
        title="clamp() returns the wrong value for in-range input",
        body=(
            "clamp(x, low, high) in bounds.py returns low when x is already within "
            "[low, high], instead of returning x unchanged. Fix it so an in-range "
            "value is returned as-is."
        ),
        category="bug",
        dir_name="clamp",
        module="bounds.py",
        test="check_bounds.py",
    ),
]

_BY_ID = {f.id: f for f in FIXTURES}


def list_fixtures() -> list[Fixture]:
    return list(FIXTURES)


def get_fixture(fixture_id: str) -> Fixture | None:
    return _BY_ID.get(fixture_id)
