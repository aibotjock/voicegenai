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


def compute_wer(hypothesis: str, reference: str) -> float:
    ref = _tokens(reference)
    hyp = _tokens(hypothesis)
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
