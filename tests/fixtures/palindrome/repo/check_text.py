from text import is_palindrome


def test_lowercase_palindrome():
    assert is_palindrome("racecar") is True


def test_mixed_case_palindrome():
    assert is_palindrome("Racecar") is True


def test_not_a_palindrome():
    assert is_palindrome("hello") is False
