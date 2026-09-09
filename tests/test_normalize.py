"""Normalization rule table tests — every rule has a test (spec §4/§12).

This file is the executable form of docs/text-normalization.md. Rule ORDER is
part of the contract (URLs before numbers, phone before integers, ranges
before percentages, glossary after normalization).
"""
import pytest

from presence_sidecar.text_pipeline.normalize import normalize


CASES = [
    # (rule, input, expected spoken form)
    ("integer-grouped", "1,234 users", "one thousand two hundred thirty-four users"),
    ("integer-large", "We have 1200000 customers.", "We have one million two hundred thousand customers."),
    ("decimal", "Pi is 3.14159 here.", "Pi is three point one four one five nine here."),
    ("decimal-2", "2.5 times faster", "two point five times faster"),
    ("percentage", "42.5% growth", "forty-two point five percent growth"),
    ("percent-range", "Ship 10-20% faster.", "Ship ten to twenty percent faster."),
    ("currency-symbol", "It costs $1,234.56.", "It costs one thousand two hundred thirty-four and fifty-six cents dollars."),
    ("currency-scale", "$1.2 million plan", "one point two million dollars plan"),
    ("currency-code", "Cost 500 EUR today.", "Cost five hundred euro today."),
    ("currency-symbol-code", "$1,234.56 USD", "one thousand two hundred thirty-four and fifty-six cents US dollars"),
    ("ordinal", "the 2nd and 121st and 100th", "the second and one hundred twenty-first and one hundredth"),
    ("fraction", "1/2 plus 3/4", "one half plus three quarters"),
    ("version", "v2.4.1 shipped", "version two point four point one shipped"),
    ("date-iso", "on 2026-09-08 we ship", "on September 8, twenty twenty-six we ship"),
    ("date-us", "by 09/08/2026 ok", "by September 8, twenty twenty-six ok"),
    ("time-ampm", "at 9:45 AM sharp", "at nine forty-five AM sharp"),
    ("time-24h", "at 14:30 sharp", "at two thirty PM sharp"),
    ("time-seconds", "14:30:45", "two thirty PM and forty-five seconds"),
    ("midnight", "00:00", "midnight"),
    ("noon", "12:00 PM", "noon"),
    ("range", "3-5 days", "three to five days"),
    ("year-range", "1910-1945 era", "nineteen ten to nineteen forty-five era"),
    ("year", "since 2026", "since twenty twenty-six"),
    ("decade", "the 1990s were great", "the nineteen nineties were great"),
    ("decade-2010s", "The 2010s cloud shift", "The two tens cloud shift"),
    ("phone-us", "call 415-555-0132 now", "call four one five, five five five, zero one three two now"),
    ("phone-intl", "call +1 (415) 555-0132 now", "call plus one, four one five, five five five, zero one three two now"),
    ("url", "Visit https://presence.studio/docs/guide.", "Visit presence dot studio slash docs slash guide"),
    ("email", "mail jane.doe@company.io now", "mail jane doe at company dot io now"),
    ("hex", "use #FF5733", "use hash F F five seven three three"),
    ("units-loose", "It weighs 10 kg.", "It weighs ten kilograms."),
    ("units-tight", "10km/h and 5GB", "ten kilometers per hour and five gigabytes"),
    ("units-temp", "37 °C outside", "thirty-seven degrees Celsius outside"),
    ("acronym", "fix the API today", "fix the A P I today"),
    ("acronym-dotted", "the U.S. system", "the U S system"),
    ("roman", "chapter IV and IX", "chapter four and nine"),
    ("ampersand", "R&D team", "R and D team"),
    ("at-symbol", "sign up @ noon", "sign up at noon"),
    ("emoji", "Hello 🎉 world 🚀", "Hello world"),
    ("markdown", "## Title\n\n**bold** and [link](https://x.com) and `code`",
     "Title\n\nbold and link and code"),
    ("whitespace", "Extra   spaces\tand lines.", "Extra spaces and lines."),
]


@pytest.mark.parametrize("rule,text,expected", CASES)
def test_rule(rule, text, expected):
    result = normalize(text)
    assert result.text == expected, f"[{rule}] got {result.text!r}"


def test_applied_rules_reported():
    r = normalize("Ship 10-20% by 2026.")
    assert "percent-range" in r.applied or "range-percent" in r.applied
    assert "year" in r.applied


def test_emoji_note():
    r = normalize("hi 🎉")
    assert any(n.kind == "emoji-stripped" for n in r.notes)


def test_small_integers_left_for_engine():
    # small integers are deliberately passed through: engines read them
    r = normalize("We grew to 42 people.")
    assert "42" in r.text


def test_markdown_bullet_strip():
    r = normalize("- item one\n- item two")
    assert r.text == "item one\nitem two"


def test_idempotent():
    once = normalize("Ship 42.5% of $1.2 million by 2026-09-08 at 14:30.").text
    twice = normalize(once).text
    assert once == twice
