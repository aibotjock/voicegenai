"""Segmentation tests (spec §4): sentences, abbreviation guards, long-sentence
splitting, paragraph tracking, markup metadata mapping."""
from presence_sidecar.text_pipeline.segment import (
    segment_script, split_sentences, MAX_SEGMENT_CHARS,
)


def test_simple_split():
    text = "One sentence here. Two sentences there. And a third one."
    out = split_sentences(text)
    assert [s for s, _ in out] == [
        "One sentence here.", "Two sentences there.", "And a third one.",
    ]


def test_abbreviation_guard():
    text = "Mr. Smith spoke. Dr. Jones replied. Prof. Lee left."
    out = split_sentences(text)
    assert len(out) == 3
    assert out[0][0] == "Mr. Smith spoke."


def test_decimal_not_split():
    text = "Pi is 3.14 exactly. It is fine."
    out = split_sentences(text)
    assert out[0][0] == "Pi is 3.14 exactly."


def test_paragraph_indices():
    text = "First paragraph line.\n\nSecond paragraph line."
    out = split_sentences(text)
    assert out[0][1] == 0 and out[1][1] == 1


def test_long_sentence_split_at_clause_then_space():
    words = "word " * 80
    long_sentence = f"Start {words.strip()}, clause end here finally done."
    segs = segment_script(long_sentence)
    assert all(len(s.text) <= MAX_SEGMENT_CHARS for s in segs)
    assert len(segs) >= 2


def test_paragraph_start_flags():
    text = "Para one first. Para one second.\n\nPara two first."
    segs = segment_script(text)
    starts = [s.is_paragraph_start for s in segs]
    assert starts == [True, False, True]


def test_markup_metadata_maps_to_segment():
    text = "Steady intro. [slow] Deliberate close."
    from presence_sidecar.text_pipeline.markup import parse_markup
    phrases = parse_markup(text)
    segs = segment_script(text, phrases)
    slow = [s for s in segs if "Deliberate" in s.text]
    assert slow and abs(slow[0].pace - 0.92) < 1e-9


def test_wrapped_lines_joined():
    text = "This sentence is\nwrapped across two lines. Second sentence."
    out = split_sentences(text)
    assert out[0][0] == "This sentence is wrapped across two lines."


def test_empty_script():
    assert split_sentences("") == []
    assert split_sentences("   \n\n  ") == []
