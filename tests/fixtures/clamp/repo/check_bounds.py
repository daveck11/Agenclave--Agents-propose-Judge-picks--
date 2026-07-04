from bounds import clamp


def test_within_range_unchanged():
    assert clamp(5, 0, 10) == 5


def test_below_low():
    assert clamp(-3, 0, 10) == 0


def test_above_high():
    assert clamp(20, 0, 10) == 10
