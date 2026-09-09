"""Deterministic English number-to-words core.

Pure functions, no side effects. Every rule is unit-tested (tests/test_numbers.py).
Style: US presentation style — no "and" between hundreds and tens
("one thousand two hundred thirty-four").
"""
from __future__ import annotations

_ONES = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen",
]
_TENS = [
    "", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
    "eighty", "ninety",
]
_SCALES = ["", "thousand", "million", "billion", "trillion"]

_ORDINAL_SUFFIX = {
    1: "st", 2: "nd", 3: "rd", 4: "th", 5: "th", 6: "th", 7: "th",
    8: "th", 9: "th", 0: "th",
}

_FRACTIONS = {
    (1, 2): "one half",
    (1, 3): "one third",
    (2, 3): "two thirds",
    (1, 4): "one quarter",
    (3, 4): "three quarters",
    (1, 8): "one eighth",
    (3, 8): "three eighths",
    (5, 8): "five eighths",
    (7, 8): "seven eighths",
    (1, 16): "one sixteenth",
    (3, 16): "three sixteenths",
    (5, 16): "five sixteenths",
    (7, 16): "seven sixteenths",
    (9, 16): "nine sixteenths",
    (11, 16): "eleven sixteenths",
    (13, 16): "thirteen sixteenths",
    (15, 16): "fifteen sixteenths",
}


def _three_digits(n: int) -> str:
    """0..999 -> words (empty string for 0)."""
    parts: list[str] = []
    if n >= 100:
        parts.append(_ONES[n // 100] + " hundred")
        n %= 100
    if n >= 20:
        tens = _TENS[n // 10]
        rem = n % 10
        parts.append(f"{tens}-{_ONES[rem]}" if rem else tens)
        n = 0
    elif n > 0:
        parts.append(_ONES[n])
    return " ".join(parts)


def int_to_words(n: int) -> str:
    """Integer -> words. Supports 0..999,999,999,999,999 (quadrillions)."""
    if n < 0:
        return "minus " + int_to_words(-n)
    if n == 0:
        return "zero"
    if n >= 10**24:
        raise ValueError(f"number out of supported range: {n}")
    chunks: list[str] = []
    i = 0
    while n > 0 and i < len(_SCALES) + 1:
        rem = n % 1000
        if rem:
            chunk = _three_digits(rem)
            scale = _SCALES[i] if i < len(_SCALES) else "quadrillion"
            chunks.append(f"{chunk} {scale}".strip())
        n //= 1000
        i += 1
    return " ".join(reversed(chunks))


def digit_pairs_year(year: int) -> str:
    """1900..2099 -> 'nineteen ninety-nine' / 'twenty twenty-six' style.

    2000 -> 'two thousand'; 1990 -> 'nineteen ninety'; 2026 -> 'twenty
    twenty-six'. Outside the range, plain words.
    """
    if 1900 <= year <= 2099:
        tens = year // 100
        rest = year % 100
        if rest == 0:
            return int_to_words(year)
        return f"{int_to_words(tens)} {int_to_words(rest)}"
    return int_to_words(year)


def year_to_words(year: int) -> str:
    return digit_pairs_year(year)


def decimal_to_words(int_part: int, frac_digits: str) -> str:
    """3.14159 -> 'three point one four one five nine'."""
    return f"{int_to_words(int_part)} point " + " ".join(_ONES[int(d)] for d in frac_digits)


_TENS_ORDINAL = {
    "twenty": "twentieth", "thirty": "thirtieth", "forty": "fortieth",
    "fifty": "fiftieth", "sixty": "sixtieth", "seventy": "seventieth",
    "eighty": "eightieth", "ninety": "ninetieth",
}


_SMALL_ORDINAL = {"one": "first", "two": "second", "three": "third",
                   "eleven": "eleventh", "twelve": "twelfth", "thirteen": "thirteenth"}


def ordinal_to_words(n: int) -> str:
    """121 -> 'one hundred twenty-first'; 11 -> 'eleventh'; 100 -> 'one hundredth'."""
    if n < 1:
        raise ValueError("no zero or negative ordinals")
    words = int_to_words(n).split(" ")
    last = words[-1]
    mod100 = n % 100
    # hyphenated compound: 'twenty-one' -> 'twenty-first'
    if "-" in last and mod100 not in (11, 12, 13):
        tens_part, small = last.split("-", 1)
        if small in ("one", "two", "three"):
            words[-1] = f"{tens_part}-{_SMALL_ORDINAL[small]}"
            return " ".join(words)
    if mod100 in (11, 12, 13) and last in ("eleven", "twelve", "thirteen"):
        words[-1] = _SMALL_ORDINAL[last]
        return " ".join(words)
    if mod100 not in (11, 12, 13) and last in ("one", "two", "three"):
        words[-1] = _SMALL_ORDINAL[last]
        return " ".join(words)
    if last in _TENS_ORDINAL:
        words[-1] = _TENS_ORDINAL[last]
        return " ".join(words)
    if last.endswith("th"):  # e.g. 'fifteen', 'eighteen'
        return " ".join(words)
    words[-1] = last + "th"
    return " ".join(words)


def fraction_to_words(num: int, den: int) -> str:
    if den == 0:
        raise ValueError("division by zero in fraction")
    key = (num, den)
    if key in _FRACTIONS:
        return _FRACTIONS[key]
    if num == 1:
        return f"one over {int_to_words(den)}"
    return f"{int_to_words(num)} over {int_to_words(den)}"


def phone_group_words(digits: str) -> str:
    """Phone digits are always spoken one by one."""
    return " ".join(_ONES[int(d)] for d in digits)
