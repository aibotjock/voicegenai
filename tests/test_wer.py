"""WER self-check tests (spec §5.4/§12): DP, gate, canonical comparison."""
from presence_sidecar.asr.wer import (
    compute_wer, check_segment, canonical_for_wer, levenshtein, WER_THRESHOLD,
)


def test_levenshtein_basics():
    assert levenshtein([], []) == 0
    assert levenshtein(["a"], []) == 1
    assert levenshtein(["a", "b"], ["a"]) == 1
    assert levenshtein(["k", "i", "t", "t", "e", "n"],
                       ["s", "i", "t", "t", "i", "n", "g"]) == 3


def test_perfect_match():
    assert compute_wer("Good morning everyone", "Good morning everyone") == 0.0


def test_one_substitution():
    # ref = 3 tokens; hypothesis differs by substitution+deletion -> 2/3
    wer = compute_wer("Good morning every one", "Good morning everyone")
    assert abs(wer - 2 / 3) < 1e-9


def test_digit_forms_canonicalized():
    # ASR writes digits; script is spoken-form words — same content
    assert compute_wer("9 countries", "nine countries") == 0.0
    assert compute_wer("12,000 customers", "twelve thousand customers") == 0.0


def test_acronym_forms_canonicalized():
    assert compute_wer("The API works", "The A P I works") == 0.0


def test_version_forms_canonicalized():
    assert compute_wer("version 2.4.1 shipped", "version two point four point one shipped") == 0.0


def test_garbled_segment_flagged():
    check = check_segment("totally unrelated words here",
                          "Good morning everyone and welcome")
    assert not check.ok
    assert check.wer > WER_THRESHOLD


def test_flag_threshold_boundary():
    ok = check_segment("a b c", "a b c d e f g h i")  # 6/9 deletions = 0.67
    assert not ok.ok


def test_canonicalization_is_deterministic():
    a = canonical_for_wer("Ship 42.5% by 2026.")
    b = canonical_for_wer("Ship 42.5% by 2026.")
    assert a == b


def test_retries_surfaced_not_silent():
    check = check_segment("wrong words", "expected words here", attempts=3)
    assert check.attempts == 3 and not check.ok
