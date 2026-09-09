"""WER computation — the accuracy self-check core.

Pure-Python Levenshtein (deterministic, dependency-free). The gate:
WER > 8% -> the segment is flagged in the UI (badge + one-click retry, up to
3 automatic retries with different seeds, then a user decision). Never
silently accepted, never silently auto-retried past 3.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

WER_THRESHOLD = 0.08
MAX_AUTO_RETRIES = 3

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def _tokens(text: str) -> list[str]:
    t = _PUNCT.sub(" ", text.lower())
    return [w for w in t.split() if w]


def levenshtein(a: list[str], b: list[str]) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cur.append(min(
                prev[j] + 1,        # deletion
                cur[j - 1] + 1,     # insertion
                prev[j - 1] + (ca != cb),  # substitution
            ))
        prev = cur
    return prev[-1]


_PUNCT_CHARS = ".,;:!?\"'()[]{}"

_WORD_NUM = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
    "ninety": 90,
}
_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven",
         "eight", "nine"]
_WORD_NUM_COMPOUND = {}
for _t, _tn in (("twenty", 20), ("thirty", 30), ("forty", 40), ("fifty", 50),
                ("sixty", 60), ("seventy", 70), ("eighty", 80), ("ninety", 90)):
    for _u in range(1, 10):
        _WORD_NUM_COMPOUND[f"{_t}-{_ONES[_u]}"] = _tn + _u
_WORD_SCALES = {"hundred": 100, "thousand": 1_000, "million": 1_000_000,
                "billion": 1_000_000_000, "trillion": 1_000_000_000_000}


def _digitize(text: str) -> str:
    """Replace word-numbers with digits so ASR digit-forms and spoken-form
    words compare equal (content accuracy, not formatting).
    'twelve thousand' -> '12000', 'twenty-four' -> '24', 'nine' -> '9'."""
    out: list[str] = []
    i = 0
    words = text.split()
    n = len(words)
    while i < n:
        w = words[i].lower().strip(_PUNCT_CHARS)
        if w in _WORD_NUM or w in _WORD_NUM_COMPOUND or w in _WORD_SCALES:
            total = 0
            current = 0
            while i < n:
                w2 = words[i].lower().strip(_PUNCT_CHARS)
                v = _WORD_NUM.get(w2, _WORD_NUM_COMPOUND.get(w2))
                s = _WORD_SCALES.get(w2)
                if v is not None:
                    current += v
                elif s is not None:
                    current = (current or 1) * s
                    if s >= 1_000:
                        total += current
                        current = 0
                else:
                    break
                i += 1
            out.append(str(total + current))
        else:
            out.append(words[i])
            i += 1
    return " ".join(out)


def canonical_for_wer(text: str) -> str:
    """Canonical token form for WER comparison.

    Applies the deterministic spoken-form normalization (so ASR digit forms
    and the normalized script collapse to the same surface), then digitizes
    number-words so 'nine' == '9'. Used on BOTH hypothesis and reference —
    the gate measures content accuracy, not formatting."""
    from ..text_pipeline.normalize import normalize
    norm = normalize(text).text
    return _digitize(norm)


def compute_wer(hypothesis: str, reference: str) -> float:
    ref = _tokens(canonical_for_wer(reference))
    hyp = _tokens(canonical_for_wer(hypothesis))
    if not ref:
        return 0.0 if not hyp else 1.0
    return levenshtein(ref, hyp) / len(ref)


@dataclass
class WerCheck:
    wer: float
    ok: bool
    hypothesis: str
    reference: str
    attempts: int = 1

    def to_dict(self) -> dict:
        return {
            "wer": round(self.wer, 4),
            "ok": self.ok,
            "threshold": WER_THRESHOLD,
            "attempts": self.attempts,
            "hypothesis": self.hypothesis,
        }


def check_segment(hypothesis: str, reference: str,
                  attempts: int = 1) -> WerCheck:
    wer = compute_wer(hypothesis, reference)
    return WerCheck(
        wer=wer, ok=wer <= WER_THRESHOLD,
        hypothesis=hypothesis, reference=reference, attempts=attempts,
    )
