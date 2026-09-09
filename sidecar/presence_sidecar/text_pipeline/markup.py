"""Prosody markup parsing (minimal, P0).

Tokens (case-insensitive):
  [pause 300ms]      explicit pause before the following phrase (50–2000 ms)
  [emphasis: word]   marks the given word as emphasized (the token itself
                     carries the word; it is spoken in place)
  [slow]             pace x0.92 for the following phrase
  [fast]             pace x1.08 for the following phrase
  [normal]           resets pace to 1.0

"[phrase]" = up to the next sentence-ending punctuation (. ! ? ; :) or the end
of the text. Tokens are invisible to the reader; the parser returns structure
the DSP layer maps to per-phrase pace/level/EQ multipliers (Layer A).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

PACE_SLOW = 0.92
PACE_FAST = 1.08

_PAUSE_RE = re.compile(r"\[\s*pause\s+(\d{2,4})\s*m?s?\]\s*", re.I)
_EMPHASIS_RE = re.compile(r"\[\s*emphasis\s*:\s*([^\]\n]+?)\s*\]\s*", re.I)
_SLOW_RE = re.compile(r"\[\s*slow\s*\]\s*", re.I)
_FAST_RE = re.compile(r"\[\s*fast\s*\]\s*", re.I)
_NORMAL_RE = re.compile(r"\[\s*normal\s*\]\s*", re.I)


@dataclass
class Phrase:
    text: str
    pace: float = 1.0
    emphasis: list[str] = field(default_factory=list)
    pause_before_ms: int = 0
    notes: list[str] = field(default_factory=list)


def _clamp_pause(ms: int) -> int:
    return max(50, min(2000, ms))


def parse_markup(text: str) -> list[Phrase]:
    """Parse markup tokens into phrases. Unknown [brackets] are kept verbatim
    with a note (never silently dropped)."""
    phrases: list[Phrase] = []
    cur_text: list[str] = []
    pace = 1.0
    emphasis: list[str] = []
    pause = 0
    notes: list[str] = []

    def flush(end: bool) -> None:
        nonlocal cur_text, pace, emphasis, pause, notes
        chunk = "".join(cur_text).strip(" \t")
        if chunk or not end:
            if chunk:
                phrases.append(Phrase(
                    text=chunk, pace=pace, emphasis=emphasis,
                    pause_before_ms=pause, notes=notes,
                ))
        cur_text, pace, emphasis, pause, notes = [], 1.0, [], 0, []

    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "[":
            m = _PAUSE_RE.match(text, i)
            if m:
                flush(True)
                pause = _clamp_pause(int(m.group(1)))
                i = m.end()
                continue
            m = _EMPHASIS_RE.match(text, i)
            if m:
                word = m.group(1).strip()
                if word:
                    emphasis.append(word)
                    cur_text.append(word)
                i = m.end()
                continue
            m = _SLOW_RE.match(text, i)
            if m:
                pace *= PACE_SLOW
                notes.append("pace:slow")
                i = m.end()
                continue
            m = _FAST_RE.match(text, i)
            if m:
                pace *= PACE_FAST
                notes.append("pace:fast")
                i = m.end()
                continue
            m = _NORMAL_RE.match(text, i)
            if m:
                pace = 1.0
                notes.append("pace:normal")
                i = m.end()
                continue
            # unknown bracket: keep verbatim
            cur_text.append(ch)
            i += 1
            continue
        if ch in ".!?;:" and (i + 1 >= n or text[i + 1] in " \n\t\"'"):
            cur_text.append(ch)
            i += 1
            flush(True)
            continue
        cur_text.append(ch)
        i += 1
    flush(False)
    # drop leading empty phrases
    while phrases and not phrases[0].text.strip():
        phrases.pop(0)
    return phrases
