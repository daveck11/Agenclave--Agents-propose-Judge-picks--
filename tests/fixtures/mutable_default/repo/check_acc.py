from acc import collect


def test_independent_calls():
    assert collect(1) == [1]
    assert collect(2) == [2]
