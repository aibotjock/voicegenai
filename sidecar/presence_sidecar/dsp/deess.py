"""Dedicated de-ess stage (Python, band-split gain reduction, 6-9 kHz).

FFmpeg has no native de-esser, so this stage runs between the compressor
(graph A) and the limiter (graph B). Algorithm:

  1. bandpass the signal (4th-order Butterworth, 6-9 kHz)
  2. compute an asymmetric envelope (IIR one-pole release + short max window
     for the attack response) — vectorized, deterministic
  3. above the threshold, reduce the BAND by a soft-knee ratio gain
  4. y_out = y - band + reduced_band   (only sibilant energy is touched)

Golden-file tested (tests/test_dsp_golden.py).
"""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, lfilter, sosfilt
from scipy.ndimage import maximum_filter1d


def _envelope(x: np.ndarray, sr: int, attack_ms: float, release_ms: float) -> np.ndarray:
    a = 1.0 - np.exp(-1.0 / max(sr * release_ms / 1000.0, 1e-6))
    env = lfilter([a], [1.0, -(1.0 - a)], x)
    win = max(1, int(sr * attack_ms / 1000.0))
    if win > 1:
        env = maximum_filter1d(env, size=win)
    return env


def deess(
    y: np.ndarray,
    sr: int = 48000,
    band: tuple[float, float] = (6000.0, 9000.0),
    threshold_db: float = -26.0,
    ratio: float = 4.0,
    attack_ms: float = 5.0,
    release_ms: float = 80.0,
    knee_db: float = 6.0,
) -> np.ndarray:
    """Apply band-split de-essing. Returns a float32 array of the same shape."""
    if y.size == 0:
        return y
    y = y.astype(np.float64, copy=True)
    nyq = sr / 2.0
    lo = max(band[0] / nyq, 1e-4)
    hi = min(band[1] / nyq, 1.0 - 1e-4)
    if lo >= hi:
        return y.astype(np.float32)
    sos = butter(4, [lo, hi], btype="band", output="sos")
    band_sig = sosfilt(sos, y)
    env = _envelope(np.abs(band_sig), sr, attack_ms, release_ms)
    thresh = 10.0 ** (threshold_db / 20.0)
    over_db = 20.0 * np.log10(np.maximum(env, 1e-9) / thresh)
    excess = np.maximum(over_db, 0.0)
    knee = max(knee_db, 0.5)
    gain_db = np.where(
        excess <= knee, excess, knee + np.maximum(excess - knee, 0.0) / ratio
    )
    gain = np.power(10.0, -gain_db / 20.0)
    reduced = band_sig * gain
    out = y - band_sig + reduced
    return out.astype(np.float32)


def process_file(in_path: str, out_path: str, sr: int = 48000, **kw) -> dict:
    """File-level wrapper used by the runner. Returns reduction stats."""
    import soundfile as sf
    y, rate = sf.read(in_path, dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = y.mean(axis=1)
    out = deess(y, sr=rate, **kw)
    sf.write(out_path, out, rate, subtype="FLOAT")
    env = _envelope(np.abs(out), rate, kw.get("attack_ms", 5.0),
                    kw.get("release_ms", 80.0))
    thresh = 10.0 ** (kw.get("threshold_db", -26.0) / 20.0)
    active = float(np.mean(env > thresh))
    return {"sr": int(rate), "samples": int(out.size), "active_fraction": active}
