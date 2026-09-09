"""Unit tests for the number-to-words core (every rule, per spec §4/§12)."""
import pytest

from presence_sidecar.text_pipeline import numbers as N


def test_int_to_words_basics():
    assert N.int_to_words(0) == "zero"
    assert N.int_to_words(1) == "one"
    assert N.int_to_words(19) == "nineteen"
    assert N.int_to_words(20) == "twenty"
    assert N.int_to_words(42) == "forty-two"
    assert N.int_to_words(100) == "one hundred"
    assert N.int_to_words(115) == "one hundred fifteen"
    assert N.int_to_words(121) == "one hundred twenty-one"
    assert N.int_to_words(999) == "nine hundred ninety-nine"
    assert N.int_to_words(1000) == "one thousand"
    assert N.int_to_words(1234) == "one thousand two hundred thirty-four"
    assert N.int_to_words(1_000_000) == "one million"
    assert N.int_to_words(1_234_567) == (
        "one million two hundred thirty-four thousand five hundred sixty-seven"
    )
    assert N.int_to_words(-5) == "minus five"
    assert N.int_to_words(2_000_000_000) == "two billion"
    assert N.int_to_words(1_000_000_000_000) == "one trillion"


def test_int_to_words_range():
    with pytest.raises(ValueError):
        N.int_to_words(10**24)


def test_year_style():
    assert N.year_to_words(2026) == "twenty twenty-six"
    assert N.year_to_words(1990) == "nineteen ninety"
    assert N.year_to_words(1945) == "nineteen forty-five"
    assert N.year_to_words(2000) == "two thousand"
    assert N.year_to_words(1910) == "nineteen ten"
    assert N.year_to_words(1899) == "one thousand eight hundred ninety-nine"


def test_decimal():
    assert N.decimal_to_words(3, "14159") == "three point one four one five nine"
    assert N.decimal_to_words(2, "5") == "two point five"
    assert N.decimal_to_words(0, "05") == "zero point zero five"


def test_ordinals():
    assert N.ordinal_to_words(1) == "first"
    assert N.ordinal_to_words(2) == "second"
    assert N.ordinal_to_words(3) == "third"
    assert N.ordinal_to_words(4) == "fourth"
    assert N.ordinal_to_words(11) == "eleventh"
    assert N.ordinal_to_words(12) == "twelfth"
    assert N.ordinal_to_words(13) == "thirteenth"
    assert N.ordinal_to_words(21) == "twenty-first"
    assert N.ordinal_to_words(22) == "twenty-second"
    assert N.ordinal_to_words(23) == "twenty-third"
    assert N.ordinal_to_words(24) == "twenty-fourth"
    assert N.ordinal_to_words(100) == "one hundredth"
    assert N.ordinal_to_words(101) == "one hundred first"
    assert N.ordinal_to_words(110) == "one hundred tenth"
    assert N.ordinal_to_words(111) == "one hundred eleventh"
    assert N.ordinal_to_words(112) == "one hundred twelfth"
    assert N.ordinal_to_words(121) == "one hundred twenty-first"
    assert N.ordinal_to_words(1112) == "one thousand one hundred twelfth"
    assert N.ordinal_to_words(1000) == "one thousandth"
    with pytest.raises(ValueError):
        N.ordinal_to_words(0)
    with pytest.raises(ValueError):
        N.ordinal_to_words(-3)


def test_fractions():
    assert N.fraction_to_words(1, 2) == "one half"
    assert N.fraction_to_words(3, 4) == "three quarters"
    assert N.fraction_to_words(1, 8) == "one eighth"
    assert N.fraction_to_words(7, 8) == "seven eighths"
    assert N.fraction_to_words(2, 5) == "two over five"
    assert N.fraction_to_words(1, 5) == "one over five"
    with pytest.raises(ValueError):
        N.fraction_to_words(1, 0)


def test_phone_groups():
    assert N.phone_group_words("415") == "four one five"
    assert N.phone_group_words("0132") == "zero one three two"
