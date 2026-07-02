from mathx import factorial


def test_base_case():
    assert factorial(0) == 1


def test_five():
    assert factorial(5) == 120
