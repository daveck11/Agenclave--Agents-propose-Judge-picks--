from fizzbuzz import fizzbuzz


def test_multiples_of_fifteen():
    assert fizzbuzz(15) == "FizzBuzz"
    assert fizzbuzz(30) == "FizzBuzz"


def test_three_and_five():
    assert fizzbuzz(9) == "Fizz"
    assert fizzbuzz(10) == "Buzz"


def test_plain_number():
    assert fizzbuzz(7) == "7"
