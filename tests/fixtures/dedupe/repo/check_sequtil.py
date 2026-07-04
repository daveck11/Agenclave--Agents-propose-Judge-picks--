from sequtil import unique


def test_preserves_first_seen_order():
    assert unique([3, 1, 3, 2, 1]) == [3, 1, 2]


def test_no_duplicates_unchanged():
    assert unique(["a", "b", "c"]) == ["a", "b", "c"]
