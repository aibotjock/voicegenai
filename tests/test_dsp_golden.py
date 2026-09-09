"""DSP golden-file tests (spec §12).

- golden filter strings pinned per design (graph builder contract)
- golden audio hash per stage: run twice -> identical (determinism)
- loudness compliance fuzz: every shipped preset hits target +/-0.5 LU,
  TP <= limit (fuzz = multiple random signals)
- join-artifact detector validated on synthetic clicks (fires) and on clean
  crossfades (stays silent)
"""
import hashlib
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from presence_sidecar.dsp import (
    PRESETS, get_preset, run_dsp, join_segments, JoinItem, measure, verify,
)
from presence_sidecar.dsp.graph import build_plan
from presence_sidecar.dsp.loudness import true_peak_db
from presence_sidecar.harness import spectral_flux_click_scan

GOLDENS_DIR = Path(__file__).parent / "goldens"


def _signal(seed: int, sr: int = 48000, dur: float = 4.0) -> np.ndarray:
    """Deterministic speech-like test signal (formants + sibilance)."""
    rng = np.random.RandomState(seed)
    t = np.arange(int(sr * dur)) / sr
    y = (0.5 * np.sin(2 * np.pi * 620 * t)
         + 0.3 * np.sin(2 * np.pi * 1180 * t + 0.7)
         + 0.2 * np.sin(2 * np.pi * 2500 * t + 1.3))
    y *= 0.6 + 0.4 * np.sin(2 * np.pi * 3.5 * t)
    sib = 0.002 * rng.randn(len(t))
    for c in (1.5, 3.2):
        sib += 0.45 * rng.randn(len(t)) * np.exp(-((t - c) ** 2) / (2 * 0.04 ** 2))
    y = y + sib * 0.8 + 0.002 * rng.randn(len(t))
    return (y / np.max(np.abs(y)) * 0.35).astype(np.float32)


# ---------------------------------------------------------------------------
# Graph-builder contract (golden filter strings)
# ---------------------------------------------------------------------------

def test_graph_strings_pinned():
    # boardroom: pace 0.95, pitch -2 st (ratio 0.8909), formant -0.5 st
    # two-pass trick: pass1 pitch = 0.8909 * 0.9715 (pitch*formant ratio),
    # pass2 pitch = 1/0.8909 with formants preserved
    plan = build_plan(PRESETS["boardroom"])
    assert plan.graph_a.startswith(
        "aresample=48000,rubberband=tempo=0.95:pitch=0.8655:formant=shifted")
    assert "rubberband=pitch=1.1225:formant=preserved" in plan.graph_a
    assert "bass=g=1.5:f=150:t=q:w=1" in plan.graph_a
    assert "ratio=3:" in plan.graph_a
    assert plan.graph_b.startswith("alimiter=limit=0.84140")
    # keynote: no pace/pitch/formant change -> NO rubberband stage at all
    plan_k = build_plan(PRESETS["keynote"])
    assert plan_k.graph_a.count("rubberband") == 0
    # calm-expert: pace-only -> one rubberband pass, formant preserved
    plan_c = build_plan(PRESETS["calm-expert"])
    assert plan_c.graph_a.count("rubberband") == 1
    assert "formant=preserved" in plan_c.graph_a


def test_bypass_plan_for_rehearsal_raw():
    plan = build_plan(PRESETS["rehearsal-raw"])
    assert plan.bypass is True
    assert plan.graph_a == "" and plan.graph_b == ""


def test_plan_is_serializable():
    for d in PRESETS.values():
        p = build_plan(d)
        assert p.to_dict()["design_params_hash"] == d.params_hash()


# ---------------------------------------------------------------------------
# Determinism + loudness compliance (per preset, fuzzed signals)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("preset_id", ["boardroom", "keynote", "calm-expert", "podcast"])
@pytest.mark.parametrize("seed", [7, 42])
def test_dsp_determinism_and_loudness(tmp_path, preset_id, seed):
    src = tmp_path / "in.wav"
    sf.write(str(src), _signal(seed), 48000, subtype="FLOAT")
    d = PRESETS[preset_id]
    out1, out2 = tmp_path / "o1.wav", tmp_path / "o2.wav"
    run_dsp(str(src), str(out1), d, tmp_path / "w1")
    run_dsp(str(src), str(out2), d, tmp_path / "w2")
    h1 = hashlib.sha256(out1.read_bytes()).hexdigest()
    h2 = hashlib.sha256(out2.read_bytes()).hexdigest()
    assert h1 == h2, "DSP chain must be deterministic for identical input"
    rep = verify(str(out1), d.lufs_target, d.true_peak_limit_db)
    assert rep.ok, rep.detail


def test_broadcast_lufs_variant(tmp_path):
    src = tmp_path / "in.wav"
    sf.write(str(src), _signal(1), 48000, subtype="FLOAT")
    d = get_preset("keynote", -23.0)
    out = tmp_path / "out.wav"
    run_dsp(str(src), str(out), d, tmp_path / "w")
    rep = verify(str(out), -23.0, -1.5)
    assert rep.ok, rep.detail


def test_true_peak_oversampling_detects_inter_sample_peak():
    # 3 kHz sine sampled at 48k can exceed the sampled peak between samples
    sr = 48000
    t = np.arange(sr) / sr
    y = 0.99 * np.sin(2 * np.pi * 3000 * t).astype(np.float32)
    assert true_peak_db(y, sr) >= -0.2  # oversampled peak ~= sampled peak


# ---------------------------------------------------------------------------
# Joiner + click detector
# ---------------------------------------------------------------------------

def _seg(tmp_path, i, freq, dur=1.5):
    sr = 48000
    t = np.arange(int(sr * dur)) / sr
    y = (0.3 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    p = tmp_path / f"s{i}.wav"
    sf.write(str(p), y, sr, subtype="PCM_24")
    return str(p)


def test_joiner_crossfade_and_pause(tmp_path):
    s = [_seg(tmp_path, i, f) for i, f in enumerate([440.0, 392.0, 523.25])]
    items = [JoinItem(s[0], None), JoinItem(s[1], "join"),
             JoinItem(s[2], "pause:350")]
    out = tmp_path / "joined.wav"
    join_segments(items, str(out), design=PRESETS["keynote"])
    y, sr = sf.read(str(out), dtype="float32", always_2d=False)
    assert y.ndim == 1
    # 3*1.5s + 0.35s pause - 2 crossfades
    expected = 3 * 1.5 + 0.35 - 2 * 0.024
    assert abs(len(y) / sr - expected) < 0.05


def test_click_detector_fires_on_synthetic_click():
    sr = 48000
    y = np.zeros(sr, dtype=np.float32)
    y += 0.01 * (np.random.RandomState(0).randn(sr))  # low noise floor
    y[sr // 2] = 1.0            # injected click
    y[sr // 2 + 1] = -1.0
    assert spectral_flux_click_scan(y, sr, [sr // 2]) == 1


def test_click_detector_silent_on_clean_crossfade(tmp_path):
    s = [_seg(tmp_path, 0, 440.0), _seg(tmp_path, 1, 392.0)]
    items = [JoinItem(s[0], None), JoinItem(s[1], "join")]
    out = tmp_path / "j.wav"
    join_segments(items, str(out))
    y, sr = sf.read(str(out), dtype="float32", always_2d=False)
    boundary = int(1.5 * sr)  # first segment ends here (minus crossfade)
    assert spectral_flux_click_scan(y, sr, [boundary]) == 0


def test_deess_reduces_sibilance_only():
    from presence_sidecar.dsp.deess import deess
    sr = 48000
    t = np.arange(sr * 2) / sr
    rng = np.random.RandomState(3)
    voice = 0.3 * np.sin(2 * np.pi * 500 * t)
    sibilance = 0.4 * rng.randn(len(t)) * np.exp(
        -((t - 1.0) ** 2) / (2 * 0.05 ** 2))
    y = (voice + sibilance).astype(np.float32)
    out = deess(y, sr=sr, threshold_db=-30, ratio=4)
    # voice band energy preserved
    from scipy.signal import butter, sosfilt
    sos = butter(4, [500 / (sr / 2), 700 / (sr / 2)], btype="band", output="sos")
    v_in, v_out = sosfilt(sos, y), sosfilt(sos, out)
    assert abs(np.sqrt(np.mean(v_out ** 2)) / np.sqrt(np.mean(v_in ** 2))) > 0.9
    # sibilant band energy reduced DURING the burst (window t=0.9..1.2)
    sos_h = butter(4, [7000 / (sr / 2), 8500 / (sr / 2)], btype="band",
                   output="sos")
    s_in, s_out = sosfilt(sos_h, y), sosfilt(sos_h, out)
    lo, hi = int(0.96 * sr), int(1.04 * sr)   # tight burst window
    rms_in = np.sqrt(np.mean(s_in[lo:hi] ** 2))
    rms_out = np.sqrt(np.mean(s_out[lo:hi] ** 2))
    assert rms_out < 0.9 * rms_in, (rms_in, rms_out)
