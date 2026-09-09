"""Pronunciation glossary tests (spec §4)."""
import pytest

from presence_sidecar.text_pipeline.glossary import (
    Pronunciation, apply_glossary, compile_glossary, letter_form_words,
)


def test_say_as_replacement():
    entries = [Pronunciation(term="Solvay", say_as="say: SolVay")]
    r = apply_glossary("We use Solvay chemicals today.", entries,
                       engine_supports_phonemes=True)
    assert r.text == "We use SolVay chemicals today."
    assert r.applied == ["Solvay"]


def test_say_as_without_prefix():
    entries = [Pronunciation(term="CICS", say_as="see-eye-see-ess")]
    r = apply_glossary("CICS is fast.", entries)
    assert r.text == "see-eye-see-ess is fast."


def test_letter_form():
    entries = [Pronunciation(term="SolVay", letter_form=True)]
    r = apply_glossary("SolVay rocks.", entries)
    assert r.text == "S O L V A Y rocks."


def test_phonemes_produce_spans_not_rewrites():
    entries = [Pronunciation(term="kubernetes",
                            phonemes="K UW1 B AH0 R N EH1 T IY0 Z")]
    r = apply_glossary("Kubernetes is easy.", entries,
                       engine_supports_phonemes=True)
    assert "Kubernetes is easy." == r.text  # term kept; span for inpainting
    assert len(r.spans) == 1
    assert r.spans[0].kind == "phoneme"
    assert r.spans[0].payload == "K UW1 B AH0 R N EH1 T IY0 Z"
    s = r.spans[0]
    assert r.text[s.start:s.end] == "Kubernetes"


def test_phonemes_unsupported_engine_warns():
    entries = [Pronunciation(term="kubernetes",
                            phonemes="K UW1 B AH0 R N EH1 T IY0 Z")]
    r = apply_glossary("Kubernetes is easy.", entries,
                       engine_supports_phonemes=False)
    assert r.text == "Kubernetes is easy."
    assert not r.spans
    assert any("cannot inpaint" in w for w in r.warnings)


def test_script_scope_wins_over_profile():
    prof = [Pronunciation(term="nginx", say_as="engine-x", scope="profile")]
    script = [Pronunciation(term="nginx", say_as="en-jin-ex", scope="script")]
    merged = compile_glossary(prof, script)
    assert len(merged) == 1
    assert merged[0].say_as == "en-jin-ex"


def test_longest_term_wins():
    entries = [Pronunciation(term="voice", say_as="vox"),
               Pronunciation(term="voice clone", say_as="vox clone")]
    r = apply_glossary("a voice clone here", entries)
    assert "vox clone" in r.text


def test_case_insensitive_and_boundaries():
    entries = [Pronunciation(term="MySQL", say_as="my-sequel")]
    r = apply_glossary("mysql and MySQLx differ.", entries)
    assert "my-sequel and MySQLx differ." == r.text  # 'MySQLx' untouched


def test_validation_rejects_empty_entries():
    with pytest.raises(ValueError):
        Pronunciation(term="x")  # no pronunciation of any kind
    with pytest.raises(ValueError):
        Pronunciation(term="x", phonemes="not arpabet!")
    with pytest.raises(ValueError):
        Pronunciation(term="x", say_as="y", scope="bad-scope")


def test_letter_form_words():
    assert letter_form_words("SolVay") == "S O L V A Y"
    assert letter_form_words("3M") == "3 M"
