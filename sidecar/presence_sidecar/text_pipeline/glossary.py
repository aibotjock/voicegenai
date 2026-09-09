"""Pronunciation glossary (P0 — non-negotiable for presentations).

Applied AFTER normalization, BEFORE TTS (the order is part of the contract).

Entry kinds:
  phonemes   ARPAbet string, e.g. "S IH1 L V AH0 EY2 SH AH0 N". Engine adapters
             may inpaint phonemes (CosyVoice-class); engines without support
             fall back to say_as, then to reading the term normally (warned).
  say_as     "say: SolVay" — universal fallback; the term is replaced by the
             phrase the engine should say instead.
  letter     letter-by-word form, e.g. "S O L V A Y".

Scope: "profile" or "script". On conflict the script glossary wins.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_PHONEME_RE = re.compile(r"^[A-Z]{1,3}[0-2]?$")


def _validate_phonemes(s: str) -> None:
    tokens = s.split()
    if not tokens:
        raise ValueError("empty phoneme string")
    for t in tokens:
        if not _PHONEME_RE.fullmatch(t):
            raise ValueError(f"invalid ARPAbet token {t!r} in {s!r}")


@dataclass
class Pronunciation:
    term: str
    phonemes: str | None = None
    say_as: str | None = None
    letter_form: bool = False
    scope: str = "script"          # "profile" | "script"

    def __post_init__(self) -> None:
        if not self.term.strip():
            raise ValueError("glossary term must be non-empty")
        if not (self.phonemes or self.say_as or self.letter_form):
            raise ValueError(
                f"glossary entry for {self.term!r} needs phonemes, say_as, or letter_form"
            )
        if self.scope not in ("profile", "script"):
            raise ValueError(f"bad scope {self.scope!r}")
        if self.say_as and self.say_as.startswith("say:"):
            self.say_as = self.say_as[4:].strip()
        if self.phonemes:
            _validate_phonemes(self.phonemes)


@dataclass
class GlossarySpan:
    """A glossary match in the processed text (for engine-level inpainting).

    start/end are offsets in the returned text.
    """
    start: int
    end: int
    term: str
    kind: str                      # "phoneme" | "say_as" | "letter"
    payload: str | None = None     # phoneme string or say-as phrase
    pron: Pronunciation | None = None


@dataclass
class GlossaryResult:
    text: str
    spans: list[GlossarySpan] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    applied: list[str] = field(default_factory=list)


def letter_form_words(term: str) -> str:
    letters = [c for c in term.upper() if c.isalpha() or c.isdigit()]
    return " ".join(letters)


def compile_glossary(
    profile_entries: list[Pronunciation],
    script_entries: list[Pronunciation],
) -> list[Pronunciation]:
    """Merge profile + script glossaries; script entries win per term."""
    by_term: dict[str, Pronunciation] = {}
    for p in profile_entries:
        by_term[p.term.casefold()] = p
    for p in script_entries:
        by_term[p.term.casefold()] = p
    entries = list(by_term.values())
    # longest term first so "voice clone" beats "voice"
    return sorted(entries, key=lambda p: -len(p.term))


@dataclass
class _CompiledEntry:
    entry: Pronunciation
    pattern: re.Pattern


def _compile(entries: list[Pronunciation]) -> list[_CompiledEntry]:
    out = []
    for e in entries:
        pat = re.compile(re.escape(e.term), re.IGNORECASE)
        out.append(_CompiledEntry(entry=e, pattern=pat))
    return out


def _boundary_ok(text: str, start: int, end: int) -> bool:
    before_ok = start == 0 or not (text[start - 1].isalnum())
    after_ok = end >= len(text) or not (text[end].isalnum())
    return before_ok and after_ok


def apply_glossary(
    text: str,
    entries: list[Pronunciation],
    engine_supports_phonemes: bool = True,
) -> GlossaryResult:
    """Apply glossary entries to already-normalized text.

    Single left-to-right scan; at each position the longest matching term
    wins. Returns the rewritten text plus spans for engine-level phoneme
    inpainting (spans cover the term as written in the output).
    """
    warnings: list[str] = []
    applied: list[str] = []
    spans: list[GlossarySpan] = []
    compiled = _compile(entries)
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        matched = None
        for ce in compiled:
            m = ce.pattern.match(text, i)
            if m and m.end() > i and _boundary_ok(text, i, m.end()):
                matched = (ce, m)
                break
        if matched is None:
            out.append(text[i])
            i += 1
            continue
        ce, m = matched
        entry = ce.entry
        start = len("".join(out))
        if entry.letter_form:
            out.append(letter_form_words(entry.term))
            i = m.end()
            applied.append(entry.term)
        elif entry.say_as:
            out.append(entry.say_as)
            i = m.end()
            applied.append(entry.term)
        else:  # phonemes only
            out.append(text[i:m.end()])
            end = len("".join(out))
            if engine_supports_phonemes:
                spans.append(GlossarySpan(
                    start=start, end=end, term=entry.term,
                    kind="phoneme", payload=entry.phonemes, pron=entry,
                ))
                applied.append(entry.term)
            else:
                warnings.append(
                    f"engine cannot inpaint phonemes; {entry.term!r} will be "
                    "read normally"
                )
            i = m.end()
    return GlossaryResult(
        text="".join(out), spans=spans, warnings=warnings, applied=applied
    )
