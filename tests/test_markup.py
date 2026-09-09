"""Prosody markup tests (spec §4)."""
from presence_sidecar.text_pipeline.markup import parse_markup


def test_basic_pause():
    phrases = parse_markup("Hello. [pause 300ms] Welcome aboard.")
    assert len(phrases) >= 2
    # find the phrase after the pause
    assert any(p.pause_before_ms == 300 and "Welcome" in p.text for p in phrases)


def test_pause_clamped():
    phrases = parse_markup("[pause 9999ms] hi")
    assert phrases[0].pause_before_ms == 2000


def test_emphasis_carries_word():
    phrases = parse_markup("This is [emphasis: crucial] today.")
    joined = " ".join(p.text for p in phrases)
    assert "crucial" in joined
    assert any("crucial" in p.emphasis for p in phrases)


def test_slow_and_fast_pace():
    phrases = parse_markup("[slow] talk steadily here. [normal] then normal.")
    assert abs(phrases[0].pace - 0.92) < 1e-9
    last = phrases[-1]
    assert last.pace == 1.0


def test_fast_multiplicative():
    phrases = parse_markup("[slow] [fast] net effect here.")
    assert abs(phrases[0].pace - 0.92 * 1.08) < 1e-9


def test_unknown_brackets_kept_verbatim():
    phrases = parse_markup("keep [citation 12] intact.")
    joined = " ".join(p.text for p in phrases)
    assert "[citation 12]" in joined


def test_plain_text_single_phrase():
    phrases = parse_markup("Just one phrase.")
    assert len(phrases) == 1
    assert phrases[0].pace == 1.0
    assert phrases[0].pause_before_ms == 0


def test_emphasis_without_word_ignored():
    phrases = parse_markup("empty token [emphasis: ] here.")
    joined = " ".join(p.text for p in phrases)
    assert "empty token" in joined
