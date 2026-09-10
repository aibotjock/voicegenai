"""Capture QC: per-file checks with plain-language feedback.

Checks (heuristic, local, no model required):
  duration       30 s - 10 min usable
  snr            signal-to-noise estimate (voice activity vs floor)
  clipping       samples at/near full scale
  silence_ratio  fraction of near-silence (too much -> bad capture)
  multi_speaker  rough change-point heuristic on pitch/energy (advisory)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import soundfile as sf

MIN_DURATION_S = 30.0
MAX_DURATION_S = 600.0


@dataclass
class QcResult:
    duration_s: float
    sample_rate: int
    snr_db: float
    clipping_events: int
    max_abs: float
    silence_ratio: float
    multi_speaker_suspect: bool
    ok: bool
    issues: list


def _energy_envelope(y: np.ndarray, sr: int, frame_ms: int = 30) -> np.ndarray:
    frame = max(1, int(sr * frame_ms / 1000))
    n = len(y) // frame
    if n == 0:
        return np.array([0.0])
    y = y[: n * frame].reshape(n, frame)
    return np.sqrt(np.mean(y.astype(np.float64) ** 2, axis=1))


def qc(wav_path: str) -> QcResult:
    y, sr = sf.read(wav_path, dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = y.mean(axis=1)
    duration = len(y) / sr
    env = _energy_envelope(y, sr)
    floor = float(np.percentile(env, 5)) if env.size else 0.0
    loud = float(np.percentile(env, 95)) if env.size else 0.0
    snr = 20 * np.log10((loud + 1e-9) / (floor + 1e-9))
    clipping = int(np.sum(np.abs(y) >= 0.995))
    # silence = frames far below the LOUD level (comparing against the quiet
    # frames makes any continuous signal look 'silent')
    if env.size and loud > 1e-4:
        silence_ratio = float(np.mean(env < max(0.08 * loud, 1e-4)))
    else:
        silence_ratio = 1.0

    # multi-speaker heuristic: large sustained pitch-energy changes.
    # Advisory only.
    suspect = False
    if env.size > 20:
        med = float(np.median(env))
        if med > 0:
            high = env > 4 * med
            # long run of very different energy (>2 s) with a quiet gap
            run = 0
            max_run = 0
            for v in high:
                run = run + 1 if v else 0
                max_run = max(max_run, run)
            gap = env < 0.25 * med
            max_gap_run = run = 0
            for v in gap:
                run = run + 1 if v else 0
                max_gap_run = max(max_gap_run, run)
            if max_run > int(sr * 2.0 / 30) and max_gap_run > int(sr * 1.0 / 30):
                suspect = True

    issues: list[str] = []
    if duration < MIN_DURATION_S:
        issues.append(
            f"Recording is {duration:.0f}s; we need at least {MIN_DURATION_S:.0f}s "
            "of your voice."
        )
    if duration > MAX_DURATION_S:
        issues.append(
            f"Recording is longer than {MAX_DURATION_S / 60:.0f} minutes; we use the "
            "best 10 minutes."
        )
    if loud < 10 ** (-45 / 20):
        issues.append(
            "This recording is essentially silence. Check that your "
            "microphone is connected and selected."
        )
    elif snr < 12:
        issues.append(
            "There's a lot of background noise. A quieter room or a closer "
            "microphone will give a much better clone."
        )
    if clipping > 0:
        issues.append(
            "Some parts are too loud and got cut off (clipping). Lower the "
            "input level and record again."
        )
    if silence_ratio > 0.7:
        issues.append("Most of the file is silence. Try to keep talking.")
    if suspect:
        issues.append(
            "It looks like more than one person may be in this recording. "
            "We can only use your own voice."
        )
    ok = not any(i.startswith(("Recording is", "Some parts", "Most of"))
                 for i in issues) and snr >= 12
    return QcResult(
        duration_s=float(duration), sample_rate=int(sr), snr_db=float(snr),
        clipping_events=clipping, max_abs=float(np.max(np.abs(y))) if y.size else 0.0,
        silence_ratio=silence_ratio, multi_speaker_suspect=suspect,
        ok=ok, issues=issues,
    )


def to_dict(r: QcResult) -> dict:
    return {
        "duration_s": round(r.duration_s, 2),
        "sample_rate": r.sample_rate,
        "snr_db": round(r.snr_db, 1),
        "clipping_events": r.clipping_events,
        "max_abs": round(r.max_abs, 4),
        "silence_ratio": round(r.silence_ratio, 3),
        "multi_speaker_suspect": bool(r.multi_speaker_suspect),
        "ok": bool(r.ok),   # never leak numpy.bool_ into JSON responses
        "issues": r.issues,
    }
