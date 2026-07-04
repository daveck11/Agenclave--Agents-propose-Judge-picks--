from convert import c_to_f


def test_freezing():
    assert c_to_f(0) == 32


def test_boiling():
    assert c_to_f(100) == 212


def test_body_temp():
    assert c_to_f(37) == 98.6
