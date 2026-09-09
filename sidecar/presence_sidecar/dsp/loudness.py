"""Loudness measurement and independent verification (pyloudnorm).

Two-pass loudnorm (FFmpeg) does the work; pyloudnorm verifies the result
independently after the fact (integrated LUFS, loudness range). True peak is
measured per ITU-R BS.1770-4 (4x oversampled peak — pyloudnorm 0.2 has no
true_peak method, so we implement it). The report goes to the UI, the
sidecar text file, and the file metadata.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import soundfile as sf

try:
    import pyloudnorm as pyln
except ImportError:  # pragma: no cover
    pyln = None


@dataclass
class LoudnessReport:
    integrated_lufs: float
    true_peak_db: float
    lra_lu: float
    target_lufs: float
    tp_limit_db: float
    ok: bool
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def true_peak_db(y: np.ndarray, sr: int) -> float:
    """ITU-R BS.1770-4 style true peak: 4x oversampled maximum |sample|."""
    if y.ndim > 1:
        y = y.mean(axis=1)
    if y.size == 0:
        return -70.0
    from scipy.signal import resample_poly
    y4 = resample_poly(np.asarray(y, dtype=np.float64), 4, 1)
    peak = float(np.max(np.abs(y4)))
    if peak <= 0:
        return -70.0
    return 20.0 * np.log10(peak)


def measure(path: str) -> dict:
    if pyln is None:
        raise RuntimeError("pyloudnorm is not installed")
    y, sr = sf.read(path, dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = y.mean(axis=1)
    meter = pyln.Meter(sr)
    # pyloudnorm's block/LRA requirements are stricter than a single block
    # (LRA needs a longer window); for short clips these metrics are
    # undefined — report conservative values instead of failing.
    try:
        integrated = meter.integrated_loudness(y)
    except ValueError:
        integrated = -70.0
    try:
        lra = meter.loudness_range(y)
    except ValueError:
        lra = 0.0
    tp = true_peak_db(y, sr)
    return {
        "integrated_lufs": float(integrated) if np.isfinite(integrated) else -70.0,
        "true_peak_db": float(tp) if np.isfinite(tp) else -70.0,
        "lra_lu": float(lra) if np.isfinite(lra) else 0.0,
        "sr": int(sr),
        "samples": int(y.size),
    }


def verify(
    path: str,
    target_lufs: float = -16.0,
    tp_limit_db: float = -1.5,
    tol_lu: float = 0.5,
    tp_tol_db: float = 0.2,
) -> LoudnessReport:
    m = measure(path)
    lufs_ok = abs(m["integrated_lufs"] - target_lufs) <= tol_lu
    tp_ok = m["true_peak_db"] <= tp_limit_db + tp_tol_db
    ok = bool(lufs_ok and tp_ok)
    detail = (
        f"integrated {m['integrated_lufs']:.2f} LUFS (target {target_lufs}, "
        f"tol +/-{tol_lu} LU); true peak {m['true_peak_db']:.2f} dBTP "
        f"(limit {tp_limit_db})"
    )
    return LoudnessReport(
        integrated_lufs=m["integrated_lufs"],
        true_peak_db=m["true_peak_db"],
        lra_lu=m["lra_lu"],
        target_lufs=target_lufs,
        tp_limit_db=tp_limit_db,
        ok=ok,
        detail=detail,
    )


def post_loudnorm_tp_guard(path: str, tp_limit_db: float = -1.5) -> float:
    """If true peak exceeds the limit after loudnorm, apply a makeup gain.

    Returns the applied gain in dB (0.0 if nothing was needed). Deterministic.
    """
    m = measure(path)
    if m["true_peak_db"] <= tp_limit_db + 1e-3:
        return 0.0
    gain_db = tp_limit_db - m["true_peak_db"]
    gain = 10.0 ** (gain_db / 20.0)
    y, sr = sf.read(path, dtype="float32")
    y = (y * gain).astype(np.float32)
    sf.write(path, y, sr, subtype="FLOAT")
    return float(gain_db)
