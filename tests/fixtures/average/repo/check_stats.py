from stats import mean


def test_mean_basic():
    assert mean([2, 4, 6]) == 4


def test_mean_empty_returns_zero():
    assert mean([]) == 0
