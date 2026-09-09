"""Text pipeline facade.

Contract (order is fixed and documented):
  1. input format layer: markdown/text -> readable text (DOCX/PDF in P1)
  2. normalization (deterministic rule table)
  3. prosody markup parse
  4. glossary application (AFTER normalization, BEFORE TTS)
  5. segmentation into TTS units
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from .normalize import NormalizationResult, Note, normalize
from .glossary import (
    GlossaryResult, GlossarySpan, Pronunciation, apply_glossary, compile_glossary,
)
from .markup import Phrase, parse_markup
from .segment import Segment, segment_script


@dataclass
class PreparedScript:
    """Everything a generation job needs, in one object."""
    original_text: str
    normalized_text: str
    spoken_text: str                      # after glossary (what the engine sees)
    segments: list[Segment]
    phrases: list[Phrase]
    glossary_spans: list[GlossarySpan]
    notes: list[Note] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    applied_rules: list[str] = field(default_factory=list)
    text_sha256: str = ""

    def __post_init__(self) -> None:
        if not self.text_sha256:
            self.text_sha256 = hashlib.sha256(
                self.original_text.encode("utf-8")
            ).hexdigest()


def extract_text(content: str, fmt: str = "text") -> tuple[str, list[Note]]:
    """Input format layer. MVP: text + markdown. DOCX/PDF land in P1."""
    notes: list[Note] = []
    fmt = (fmt or "text").lower()
    if fmt in ("text", "txt", "markdown", "md"):
        if fmt in ("markdown", "md"):
            return content, notes
        return content, notes
    if fmt in ("docx", "pdf"):
        raise ValueError(
            f"import of {fmt.upper()} is not available in this build yet "
            "(P1). Please paste the text or use .md/.txt."
        )
    raise ValueError(f"unsupported input format: {fmt!r}")


def prepare_script(
    raw: str,
    fmt: str = "text",
    profile_glossary: list[Pronunciation] | None = None,
    script_glossary: list[Pronunciation] | None = None,
    engine_supports_phonemes: bool = True,
) -> PreparedScript:
    text, notes = extract_text(raw, fmt)
    norm: NormalizationResult = normalize(text)
    phrases: list[Phrase] = parse_markup(norm.text)
    entries = compile_glossary(
        profile_glossary or [], script_glossary or []
    )
    gres: GlossaryResult = apply_glossary(
        norm.text, entries, engine_supports_phonemes=engine_supports_phonemes
    )
    # Glossary rewrites can change lengths; re-derive segments from the
    # final spoken text (markup metadata mapped by containment).
    segments = segment_script(gres.text, phrases)
    return PreparedScript(
        original_text=text,
        normalized_text=norm.text,
        spoken_text=gres.text,
        segments=segments,
        phrases=phrases,
        glossary_spans=gres.spans,
        notes=notes + [Note("glossary-warning", w) for w in gres.warnings],
        warnings=gres.warnings,
        applied_rules=norm.applied,
    )
