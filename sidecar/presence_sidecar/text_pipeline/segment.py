"""Script segmentation: paragraphs -> sentences -> TTS segments.

- Paragraphs are the join unit (pause shaping happens at paragraph bounds).
- Sentences are the generation unit, capped at ~200 chars; long sentences
  are split at clause punctuation (, ; :) first, then spaces.
- Sentence splitting guards decimals ("3.14") and common abbreviations
  ("Mr. Smith" stays one sentence).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_SEGMENT_CHARS = 200

_ABBREV = {
    "mr", "mrs", "ms", "dr", "prof", "st", "vs", "e.g", "i.e", "etc", "fig",
    "no", "approx", "inc", "ltd", "co", "corp", "gen", "rep", "sen", "mt",
    "dept", "est", "vol", "chap", "u.s", "u.k",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
}

# Candidate sentence ends: [.!?] + whitespace + (optional openers) + Capital/Digit.
_SENT_END_RE = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[]*[A-Z0-9])")


def _is_abbrev(token: str) -> bool:
    return token.rstrip(".!?").casefold() in _ABBREV


def split_sentences(text: str) -> list[tuple[str, int]]:
    """Return (sentence, paragraph_index) pairs."""
    out: list[tuple[str, int]] = []
    for para_idx, raw_para in enumerate(re.split(r"\n\s*\n", text)):
        raw_para = re.sub(r"\s*\n\s*", " ", raw_para).strip()
        if not raw_para:
            continue
        start = 0
        for m in _SENT_END_RE.finditer(raw_para):
            before = raw_para[start:m.start() + 1]
            words = before.split()
            if words and _is_abbrev(words[-1]):
                continue  # abbreviation: do not split
            piece = before.strip()
            if piece:
                out.append((piece, para_idx))
            start = m.end()
        tail = raw_para[start:].strip()
        if tail:
            out.append((tail, para_idx))
    return out


@dataclass
class Segment:
    index: int
    text: str
    paragraph: int
    is_paragraph_start: bool
    pace: float = 1.0
    emphasis: list[str] = field(default_factory=list)
    pause_before_ms: int = 0
    notes: list[str] = field(default_factory=list)


def _split_long(sentence: str) -> list[str]:
    """Split a long sentence into pieces of <= MAX_SEGMENT_CHARS."""
    if len(sentence) <= MAX_SEGMENT_CHARS:
        return [sentence]
    parts = re.split(r"(?<=[,;:])\s+", sentence)
    chunks: list[str] = []
    cur = ""
    for p in parts:
        if cur and len(cur) + 1 + len(p) > MAX_SEGMENT_CHARS:
            chunks.append(cur)
            cur = p
        else:
            cur = f"{cur} {p}".strip() if cur else p
    if cur:
        chunks.append(cur)
    final: list[str] = []
    for chunk in chunks:
        if len(chunk) <= MAX_SEGMENT_CHARS:
            final.append(chunk)
            continue
        cur = ""
        for w in chunk.split(" "):
            if cur and len(cur) + 1 + len(w) > MAX_SEGMENT_CHARS:
                final.append(cur)
                cur = w
            else:
                cur = f"{cur} {w}".strip() if cur else w
        if cur:
            final.append(cur)
    return [c for c in final if c]


def segment_script(
    text: str,
    phrases: list | None = None,
) -> list[Segment]:
    """Segment normalized text into TTS segments (<= MAX_SEGMENT_CHARS).

    `phrases` (from markup.parse_markup) carries pace/emphasis/pause metadata
    onto the segment containing each phrase's start position (MVP mapping;
    the mapping is visible in the UI per the spec).
    """
    segments: list[Segment] = []
    for sentence, para_idx in split_sentences(text):
        first = True
        for piece in _split_long(sentence):
            segments.append(Segment(
                index=len(segments), text=piece, paragraph=para_idx,
                is_paragraph_start=first,
            ))
            first = False
    if phrases:
        for ph in phrases:
            key = ph.text[:20]
            if not key:
                continue
            pos = text.find(key)
            if pos == -1:
                continue
            for seg in segments:
                seg_pos = text.find(seg.text)
                if seg_pos == -1:
                    continue
                if seg_pos <= pos < seg_pos + len(seg.text):
                    seg.pace *= ph.pace
                    seg.emphasis.extend(ph.emphasis)
                    seg.pause_before_ms += ph.pause_before_ms
                    seg.notes.extend(ph.notes)
                    break
    return segments
