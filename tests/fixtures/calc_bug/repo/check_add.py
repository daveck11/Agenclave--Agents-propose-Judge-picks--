# Fixture test suite for the calc_bug sandbox. Named check_*.py (not test_*.py) so
# the project's own pytest run ignores it; verify_patch runs it explicitly inside a
# sandbox copy via `pytest check_add.py`.
from calc import add


def test_add():
    assert add(2, 3) == 5


def test_add_zero():
    assert add(0, 0) == 0
