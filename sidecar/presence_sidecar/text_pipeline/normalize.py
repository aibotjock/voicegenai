"""Deterministic text normalization (spoken form).

Fixed rule order (documented in docs/text-normalization.md). Every rule has
unit tests. The engine is a list of (name, regex, replacer) applied in order;
ordering is part of the contract (e.g. ranges before percentages, phone before
integers, glossary after normalization).

Design principle: disambiguate what TTS engines would misread (dates,
decimals, currency, versions, phones, acronyms, units); leave plain small
integers (1-999) as digits — engines read those reliably, and expansion is
only applied where the raw form is genuinely ambiguous (grouped numbers,
4+ digits, decimals, years).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import numbers as N

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclass
class Note:
    kind: str          # "emoji-stripped" | "scanned-pdf" | ...
    message: str
    count: int = 1


@dataclass
class NormalizationResult:
    text: str
    notes: list[Note] = field(default_factory=list)
    applied: list[str] = field(default_factory=list)


_MONTHS = {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
    7: "July", 8: "August", 9: "September", 10: "October", 11: "November",
    12: "December",
}
_MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

_CURRENCY_SYMBOL = {
    "$": "dollar", "€": "euro", "£": "pound", "¥": "yen", "₹": "rupee",
}
_CURRENCY_CODE = {
    "USD": "US dollar", "EUR": "euro", "GBP": "pound", "JPY": "yen",
    "CNY": "yuan", "INR": "rupee", "AUD": "Australian dollar",
    "CAD": "Canadian dollar", "CHF": "Swiss franc", "SEK": "Swedish krona",
}
_NO_CENTS = {"JPY", "CNY", "CHF", "SEK"}

# Units whose symbol may be tight against the number ("100km/h", "5GB", "37°C").
_UNITS_TIGHT: list[tuple[str, str]] = [
    ("km/hour", "kilometers per hour"),
    ("°Celsius", "degrees Celsius"),
    ("°Fahrenheit", "degrees Fahrenheit"),
    ("km/h", "kilometers per hour"),
    ("m/s", "meters per second"),
    ("GB/s", "gigabytes per second"),
    ("MB/s", "megabytes per second"),
    ("°C", "degrees Celsius"),
    ("°F", "degrees Fahrenheit"),
    ("MHz", "megahertz"), ("GHz", "gigahertz"), ("kHz", "kilohertz"),
    ("°", "degrees"),
    ("dB", "decibels"),
    ("TB", "terabytes"), ("GB", "gigabytes"), ("MB", "megabytes"),
    ("KB", "kilobytes"), ("kB", "kilobytes"),
    ("Hz", "hertz"),
]
# Units that require a space between number and symbol ("100 km").
_UNITS_LOOSE: list[tuple[str, str]] = [
    ("km", "kilometers"), ("cm", "centimeters"), ("mm", "millimeters"),
    ("mL", "milliliters"), ("µg", "micrograms"), ("mg", "milligrams"),
    ("kg", "kilograms"), ("lb", "pounds"), ("oz", "ounces"),
    ("mi", "miles"), ("ft", "feet"), ("in", "inches"),
    ("kW", "kilowatts"), ("MW", "megawatts"),
    ("ppm", "parts per million"), ("ppb", "parts per billion"),
    ("L", "liters"), ("min", "minutes"),
    ("cal", "calories"), ("J", "joules"), ("V", "volts"), ("W", "watts"),
    ("A", "amperes"), ("K", "kelvins"), ("s", "seconds"), ("m", "meters"),
    ("g", "grams"), ("h", "hours"),
]

_IN_STOPWORDS = (r"the|a|an|my|your|his|her|our|their|this|that|each|either"
                 r"|about|inside|within|between")


def _unit_alternation(units: list[tuple[str, str]]) -> str:
    frags = []
    for frag, _spoken in sorted(units, key=lambda u: -len(u[0])):
        if frag == "in":
            frags.append(r"in(?!(?:\s+" + _IN_STOPWORDS + r")\b)")
        else:
            frags.append(re.escape(frag))
    return "|".join(frags)


_UNIT_SPOKEN = {u[0]: u[1] for u in _UNITS_TIGHT + _UNITS_LOOSE}

_UNIT_TIGHT_RE = re.compile(
    r"\b(\d[\d,]*(?:\.\d+)?)\s?(" + _unit_alternation(_UNITS_TIGHT) + r")\b"
)
_UNIT_LOOSE_RE = re.compile(
    r"\b(\d[\d,]*(?:\.\d+)?)\s+(" + _unit_alternation(_UNITS_LOOSE) + r")\b"
)

_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF\U00002B00-\U00002BFF\U0000FE0F\u00a9\u00ae]"
)

# ---------------------------------------------------------------------------
# Rule replacers
# ---------------------------------------------------------------------------

def _re_markdown(m: re.Match) -> str:
    return m.group(1) if m.group(1) is not None else ""


def _re_emoji(m: re.Match) -> str:
    return " "


def _re_email(m: re.Match) -> str:
    local, domain = m.group(1), m.group(2)
    local_spoken = local.replace(".", " ").replace("_", " ")
    dom_spoken = " dot ".join(domain.split("."))
    return f"{local_spoken} at {dom_spoken}"


def _re_url(m: re.Match) -> str:
    url = re.sub(r"^(https?|ftp)://", "", m.group(0), flags=re.I)
    url = url.rstrip("/.,;:!?")
    host, _, rest = url.partition("/")
    host = host.replace("_", " ").replace("-", " ")
    host = " dot ".join(h for h in host.split(".") if h)
    parts: list[str] = [host] if host else []
    if rest:
        path = [p for p in rest.split("/") if p]
        path = [p.replace("_", " ").replace("-", " ") for p in path]
        parts.append(" slash ".join(path))
    return " slash ".join(x for x in parts if x)


def _phone_spoken(digits: str) -> str:
    """Phone digits are always spoken one by one, groups comma-separated."""
    if len(digits) == 11 and digits.startswith("1"):
        groups = [digits[1:4], digits[4:7], digits[7:]]
        return "plus one, " + ", ".join(N.phone_group_words(g) for g in groups)
    if len(digits) == 10:
        groups = [digits[:3], digits[3:6], digits[6:]]
        return ", ".join(N.phone_group_words(g) for g in groups)
    groups = [digits[i:i + 3] for i in range(0, len(digits) - 2, 3)]
    if len(digits) % 3:
        groups.append(digits[-(len(digits) % 3):])
    return ", ".join(N.phone_group_words(g) for g in groups if g)


def _re_phone(m: re.Match) -> str:
    return _phone_spoken(re.sub(r"\D", "", m.group(0)))


def _money_spoken(value: str, cents: str | None, cur: str) -> str:
    spoken = N.int_to_words(int(value))
    if cents is not None and cents != "00":
        spoken += f" and {N.int_to_words(int(cents))} cents"
    return f"{spoken} {cur}s"


def _decimal_amount_words(value: str) -> str:
    v, frac = value.split(".")
    return (f"{N.int_to_words(int(v))} point "
            + " ".join(N._ONES[int(d)] for d in frac))


def _re_currency_scale(m: re.Match) -> str:
    # "$1.2 million" -> "one point two million dollars" (never a 'cents'
    # reading when a scale word follows the amount)
    cur_name = _CURRENCY_SYMBOL[m.group(1)]
    value = m.group(2).replace(",", "")
    scale = m.group(3).lower()
    if "." in value:
        amount = _decimal_amount_words(value)
    else:
        amount = N.int_to_words(int(value))
    return f"{amount} {scale} {cur_name}s"


def _re_currency_symbol(m: re.Match) -> str:
    cur_name = _CURRENCY_SYMBOL[m.group(1)]
    value = m.group(2).replace(",", "")
    if "." in value:
        v, frac = value.split(".")
        if len(frac) == 2:  # exactly two decimals -> cents reading
            return _money_spoken(v, frac, cur_name)
        return f"{_decimal_amount_words(value)} {cur_name}s"
    return f"{N.int_to_words(int(value))} {cur_name}s"


def _re_currency_symbol_code(m: re.Match) -> str:
    # "$1,234.56 USD" -> "...US dollars" (code name wins over symbol name)
    value = m.group(2).replace(",", "")
    code = m.group(3).upper()
    name = _CURRENCY_CODE.get(code, _CURRENCY_SYMBOL.get(m.group(1), code.lower()))
    if "." in value and code not in _NO_CENTS:
        v, cents = value.split(".")
        return _money_spoken(v, cents, name)
    return f"{N.int_to_words(int(value.split('.')[0]))} {name}"


def _re_currency_code(m: re.Match) -> str:
    value = m.group(1).replace(",", "")
    code = m.group(2).upper()
    name = _CURRENCY_CODE.get(code, code.lower() + "s")
    if code in _NO_CENTS or "." not in value:
        return f"{N.int_to_words(int(value.split('.')[0]))} {name}"
    v, cents = value.split(".")
    if cents == "00":
        return f"{N.int_to_words(int(v))} {name}"
    return f"{N.int_to_words(int(v))} and {N.int_to_words(int(cents))} cents {name}"


def _re_percentage(m: re.Match) -> str:
    sign = m.group(1) or ""
    value = m.group(0)[:-1].lstrip("+-−").strip().replace(",", "")
    prefix = ""
    if sign == "+":
        prefix = "plus "
    elif sign in ("-", "−"):
        prefix = "minus "
    if "." in value:
        v, frac = value.split(".")
        amount = f"{N.int_to_words(int(v))} point " + " ".join(
            N._ONES[int(d)] for d in frac
        )
    else:
        amount = N.int_to_words(int(value))
    return f"{prefix}{amount} percent"


def _time_spoken(hour: int, minute: int, second: int | None, ampm: str) -> str:
    if hour > 12:
        ampm = "PM"
    elif hour == 0:
        ampm = "AM"
    if hour == 0 and minute == 0 and second in (None, 0):
        base = "midnight"
    elif hour == 12 and minute == 0 and ampm == "PM" and second in (None, 0):
        base = "noon"
    else:
        h12 = hour % 12 or 12
        minute_spoken = N.int_to_words(minute) if minute else "o'clock"
        base = f"{N.int_to_words(h12)} {minute_spoken}"
        if ampm:
            base += f" {ampm}"
    if second is not None:
        base += f" and {N.int_to_words(second)} seconds"
    return base


def _re_time(m: re.Match) -> str:
    hour = int(m.group(1))
    minute = int(m.group(2))
    second = int(m.group(3)) if m.group(3) else None
    ampm = (m.group(4) or "").upper()
    return _time_spoken(hour, minute, second, ampm)


def _re_time_24h(m: re.Match) -> str:
    hour = int(m.group(1))
    minute = int(m.group(2))
    second = int(m.group(3)) if m.group(3) else None
    return _time_spoken(hour, minute, second, "")


def _re_date_iso(m: re.Match) -> str:
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return f"{_MONTHS[mo]} {d}, {N.year_to_words(y)}"


def _re_date_us(m: re.Match) -> str:
    mo, d = int(m.group(1)), int(m.group(2))
    y = m.group(3)
    if len(y) == 2:
        y = str(int(y) + (1900 if int(y) >= 70 else 2000))
    return f"{_MONTHS[mo]} {d}, {N.year_to_words(int(y))}"


def _re_date_monthname(m: re.Match) -> str:
    mo = _MONTH_ABBR.get(m.group(1).lower().rstrip("."))
    if mo is None:
        return m.group(0)
    return f"{_MONTHS[mo]} {m.group(2)}, {N.year_to_words(int(m.group(3)))}"


def _re_version(m: re.Match) -> str:
    prefix = "version " if m.group(1) else ""
    parts = [m.group(2), m.group(3), m.group(4)]
    spoken = " point ".join(N.int_to_words(int(p)) for p in parts)
    if m.group(5):
        pre_spoken = " ".join(
            c.upper() if c.isalpha() else N.int_to_words(int(c))
            for c in re.findall(r"[0-9A-Za-z]+", m.group(5))
        )
        spoken += f" {pre_spoken}"
    return f"{prefix}{spoken}"


def _re_ordinal(m: re.Match) -> str:
    return N.ordinal_to_words(int(m.group(1)))


def _re_fraction(m: re.Match) -> str:
    return N.fraction_to_words(int(m.group(1)), int(m.group(2)))


def _re_decimal(m: re.Match) -> str:
    value = m.group(0).replace(",", "")
    v, frac = value.split(".")
    return N.decimal_to_words(int(v), frac)


def _re_range(m: re.Match) -> str:
    a = m.group(1).replace(",", "")
    b = m.group(2).replace(",", "")
    if len(a) == 4 and len(b) == 4 and \
            1900 <= int(a) <= 2099 and 1900 <= int(b) <= 2099:
        return f"{N.year_to_words(int(a))} to {N.year_to_words(int(b))}"
    return f"{N.int_to_words(int(a))} to {N.int_to_words(int(b))}"


def _re_unit(value: str, unit: str) -> str:
    value = value.replace(",", "")
    if "." in value:
        v, frac = value.split(".")
        amount = f"{N.int_to_words(int(v))} point " + " ".join(
            N._ONES[int(d)] for d in frac
        )
    else:
        amount = N.int_to_words(int(value))
    spoken = _UNIT_SPOKEN.get(unit, unit)
    return f"{amount} {spoken}"


def _re_unit_tight(m: re.Match) -> str:
    return _re_unit(m.group(1), m.group(2))


def _re_unit_loose(m: re.Match) -> str:
    return _re_unit(m.group(1), m.group(2))


def _re_year(m: re.Match) -> str:
    return N.year_to_words(int(m.group(0)))


_TENSIES = {
    "twenty": "twenties", "thirty": "thirties", "forty": "forties",
    "fifty": "fifties", "sixty": "sixties", "seventy": "seventies",
    "eighty": "eighties", "ninety": "nineties",
}


def _re_decade(m: re.Match) -> str:
    """1980s -> 'the nineteen eighties'; 2010s -> 'the two tens';
    2000s -> 'the two thousands'. A preceding article is captured and
    re-emitted exactly once. Non-decade endings fall through to the year
    rule (e.g. '1985s' stays literal)."""
    year = int(m.group(2))
    last_two = int(m.group(3))
    article = m.group(1) or "the "
    if last_two % 10 != 0:
        return m.group(0)
    base = "two" if year // 100 == 20 else N.int_to_words(year // 100)
    if last_two == 0:
        return f"{article}{base} thousands"
    tens_word = N._TENS[last_two // 10]
    if tens_word in _TENSIES:
        return f"{article}{base} {_TENSIES[tens_word]}"
    return f"{article}{base} tens"


def _re_int(m: re.Match) -> str:
    return N.int_to_words(int(m.group(0).replace(",", "")))


def _re_plusminus(m: re.Match) -> str:
    sign = m.group(1)
    return " plus or minus " if sign == "±" else (" plus " if sign == "+" else " minus ")


def _re_acronym_dotted(m: re.Match) -> str:
    # 'U.S. system' -> 'U S system' (dots dropped, letters spaced)
    return " ".join(re.findall(r"[A-Z]", m.group(0)))


# Words we ourselves generate (currency/time names) plus a few common
# two-letter words read as words in professional speech. Everything else
# defaults to letter-by-letter per spec (glossary can override to word form).
_ACRONYM_WORD_EXCEPTIONS = {"AM", "PM", "US", "UK", "EU", "OK"}


def _re_acronym(m: re.Match) -> str:
    word = m.group(0)
    if word in _ACRONYM_WORD_EXCEPTIONS:
        return word
    return " ".join(word)


def _roman_value(s: str) -> int | None:
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total, prev = 0, 0
    for ch in reversed(s):
        v = vals[ch]
        total += -v if v < prev else v
        prev = v
    if 1 <= total <= 3999 and _roman_canonical(total) == s:
        return total
    return None


_ROMAN_TABLE = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
                (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
                (5, "V"), (4, "IV"), (1, "I")]


def _roman_canonical(n: int) -> str:
    out = []
    for v, sym in _ROMAN_TABLE:
        while n >= v:
            out.append(sym)
            n -= v
    return "".join(out)


# ---------------------------------------------------------------------------
# Rule table (ORDER IS CONTRACT — see docs/text-normalization.md)
# ---------------------------------------------------------------------------

_MD_LINK = re.compile(r"!\[([^\]]*)\]\([^)]*\)|\[([^\]]+)\]\([^)]*\)")
_MD_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+", re.M)
_MD_BULLET = re.compile(r"^\s*(?:[-*+]\s+|\d{1,3}[.)]\s+)", re.M)
_MD_BQ = re.compile(r"^\s*>\s?", re.M)
_MD_BOLD = re.compile(r"(?<!\w)(\*{1,2}|_{1,2})([^*_\n]+)\1(?!\w)")
_MD_CODE = re.compile(r"`([^`\n]+)`")
_MD_HR = re.compile(r"^\s*([-*_])\s*(\1\s*){2,}$", re.M)
_MD_TABLE_SEP = re.compile(r"^\s*\|[\s:|-]+\|\s*$", re.M)
_MD_TABLE_ROW = re.compile(r"^\s*\|(.+)\|\s*$", re.M)

RULES: list[tuple[str, re.Pattern, object]] = [
    ("markdown-image-link", _MD_LINK, lambda m: m.group(1) or m.group(2) or ""),
    ("markdown-heading", _MD_HEADING, lambda m: ""),
    ("markdown-bullet", _MD_BULLET, lambda m: ""),
    ("markdown-blockquote", _MD_BQ, lambda m: ""),
    ("markdown-hr", _MD_HR, lambda m: "\n\n"),
    ("markdown-table-sep", _MD_TABLE_SEP, lambda m: ""),
    ("markdown-table-row", _MD_TABLE_ROW,
     lambda m: ", ".join(c.strip() for c in m.group(1).split("|")) + " "),
    ("markdown-bold-italic", _MD_BOLD, lambda m: m.group(2)),
    ("markdown-code-span", _MD_CODE, lambda m: m.group(1)),
    ("emoji-strip", _EMOJI_RE, _re_emoji),
    ("email", re.compile(r"\b([A-Za-z0-9._%+-]+)@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})\b"), _re_email),
    ("url", re.compile(r"(?:https?|ftp)://[^\s\)\]<>\"']+", re.I), _re_url),
    ("hex-color", re.compile(r"#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b"),
     lambda m: "hash " + " ".join(c.upper() if c.isalpha() else N.int_to_words(int(c)) for c in m.group(1))),
    ("phone-intl", re.compile(r"\+\d[\d\s\-().]{6,17}\d"), _re_phone),
    ("phone-us", re.compile(r"(?<![\d.])(\(?\d{3}\)?)[\s.-](\d{3})[\s.-](\d{4})(?!\d)"),
     lambda m: _phone_spoken(re.sub(r"\D", "", m.group(0)))),
    ("currency-symbol-scale", re.compile(r"([$€£¥₹])\s?(\d[\d,]*(?:\.\d+)?)\s+(million|billion|trillion)\b", re.I), _re_currency_scale),
    ("currency-symbol-code", re.compile(r"([$€£¥₹])\s?(\d[\d,]*(?:\.\d{1,2})?)\s+(USD|EUR|GBP|JPY|CNY|INR|AUD|CAD|CHF|SEK)\b", re.I), _re_currency_symbol_code),
    ("currency-symbol", re.compile(r"([$€£¥₹])\s?(\d[\d,]*(?:\.\d{1,2})?)(?!\s+(?:USD|EUR|GBP|JPY|CNY|INR|AUD|CAD|CHF|SEK)\b)"), _re_currency_symbol),
    ("currency-code", re.compile(r"\b(\d[\d,]*(?:\.\d+)?)\s?(USD|EUR|GBP|JPY|CNY|INR|AUD|CAD|CHF|SEK)\b", re.I), _re_currency_code),
    ("range-percent", re.compile(r"(\d[\d,]*(?:\.\d+)?)\s?[-–]\s?(\d[\d,]*(?:\.\d+)?)\s?%"),
     lambda m: f"{N.int_to_words(int(m.group(1).replace(',', '')))} to "
               f"{N.int_to_words(int(m.group(2).replace(',', '')))} percent"),
    ("range", re.compile(r"(?<!\d[-–—])\b(\d{1,3}(?:,\d{3})*|1[9]\d{2}|2[0]\d{2})\s?[-–—]\s?(\d{1,3}(?:,\d{3})*|1[9]\d{2}|2[0]\d{2})(?![-]\d)\b"), _re_range),
    ("decade", re.compile(
        r"((?:(?<=\s)|^)(?:the|The|a|A)\s+)?(?<![A-Za-z])((?:19|20)(\d{2}))s\b"
     ), _re_decade),
    ("percentage", re.compile(r"([+\-−])?\d[\d,]*(?:\.\d+)?\s?%"), _re_percentage),
    # NOTE: percentage replacer reads m.group(0) with the trailing '%' stripped
    ("time", re.compile(r"(?<![\d.])(\d{1,2}):(\d{2})(?::(\d{2}))?\s?(AM|PM|am|pm)\b"), _re_time),
    ("time-24h", re.compile(r"(?<![\d.])(\d{1,2}):(\d{2})(?::(\d{2}))?(?![\d:apAP])"), _re_time_24h),
    ("date-iso", re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"), _re_date_iso),
    ("date-us", re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b"), _re_date_us),
    ("date-monthname", re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b"), _re_date_monthname),
    ("fraction", re.compile(r"\b(\d{1,2})/(\d{1,3})\b"), _re_fraction),
    ("version", re.compile(r"\b(v)?(\d{1,2})\.(\d{1,2})\.(\d{1,4})(?!\.\d)(?:-([0-9A-Za-z.]+))?\b"), _re_version),
    ("ordinal", re.compile(r"\b(\d{1,4})(st|nd|rd|th)\b"), _re_ordinal),
    ("unit-tight", _UNIT_TIGHT_RE, _re_unit_tight),
    ("unit-loose", _UNIT_LOOSE_RE, _re_unit_loose),
    ("decimal", re.compile(r"\b\d{1,3}(?:,\d{3})*\.\d{1,6}\b"), _re_decimal),
    ("year", re.compile(r"(?<![\d.])(19\d{2}|20\d{2})(?![\d-])"), _re_year),
    ("integer", re.compile(r"\b\d{1,3}(?:,\d{3})+\b|\b\d{4,}\b"), _re_int),
    ("plusminus", re.compile(r"(?<=\s)([+−])\s*(?=\d)"), _re_plusminus),
    ("ampersand", re.compile(r"&"), lambda m: " and "),
    ("at-symbol", re.compile(r"(?<![\w@])@(?![\w@])"), lambda m: "at"),
    ("roman-numeral", re.compile(r"\b([IVX]{2,4})\b"),
     lambda m: N.int_to_words(v) if (v := _roman_value(m.group(1))) is not None else m.group(0)),
    ("acronym-dotted", re.compile(r"\b[A-Z](?:\.[A-Z]){1,5}\.?(?=[\s.,;:!?)\]]|$)"), _re_acronym_dotted),
    ("acronym", re.compile(r"\b[A-Z]{2,6}\b"), _re_acronym),
]

# Final pass: cosmetic whitespace (not part of the numbered table)
_WS_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"[“”]"), '"'),
    (re.compile(r"[‘’]"), "'"),
    (re.compile(r"\.{3,}"), "."),
    (re.compile(r"\s+—\s+"), " "),
    (re.compile(r"\s+–\s+"), " "),
    (re.compile(r"--"), " "),
    (re.compile(r"[ \t]{2,}"), " "),
    (re.compile(r" ?\n ?"), "\n"),
    (re.compile(r"\n{3,}"), "\n\n"),
    (re.compile(r"\t"), " "),
    (re.compile(r" \."), "."),
    (re.compile(r" ,"), ","),
]


def normalize(text: str) -> NormalizationResult:
    notes: list[Note] = []
    applied: list[str] = []
    out = text
    emoji_hits = _EMOJI_RE.findall(out)
    if emoji_hits:
        sample = " ".join(emoji_hits[:3])
        notes.append(Note("emoji-stripped", f"stripped {len(emoji_hits)} emoji ({sample!r})"))
    for name, pattern, repl in RULES:
        new = pattern.sub(repl, out) if callable(repl) else out
        if new != out:
            applied.append(name)
        out = new
    for pattern, rep in _WS_PATTERNS:
        out = pattern.sub(rep, out)
    out = re.sub(r"[ \t]+\n", "\n", out)
    out = re.sub(r"\n[ \t]+", "\n", out)
    out = "\n".join(line.strip() for line in out.split("\n"))
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return NormalizationResult(text=out, notes=notes, applied=applied)
