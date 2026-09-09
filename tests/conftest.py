import os
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

# Keep tests hermetic: isolated PRESENCE_HOME before the sidecar imports.
_TMP_HOME = Path("/tmp/presence-test-home")
if os.environ.get("PRESENCE_HOME") != str(_TMP_HOME):
    os.environ["PRESENCE_HOME"] = str(_TMP_HOME)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sidecar"))


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("PRESENCE_HOME", str(tmp_path))
    import presence_sidecar.config as cfg
    fresh = cfg.Settings()
    monkeypatch.setattr(cfg, "SETTINGS", fresh)
    yield fresh


@pytest.fixture()
def tone_wav(tmp_path):
    """1 s of 440 Hz at 48 kHz mono float32, -20 dBFS."""
    sr = 48000
    t = np.arange(sr) / sr
    y = (0.1 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    p = tmp_path / "tone.wav"
    sf.write(str(p), y, sr, subtype="FLOAT")
    return str(p)


@pytest.fixture()
def speechlike_wav(tmp_path):
    """3 s of band-limited 'speech-like' signal (formant-ish, 48 kHz mono)."""
    sr = 48000
    n = sr * 3
    t = np.arange(n) / sr
    # vowel-like formant stack with syllabic AM + a sibilant burst at 7 kHz
    y = (
        0.5 * np.sin(2 * np.pi * 700 * t)
        + 0.3 * np.sin(2 * np.pi * 1200 * t + 0.7)
        + 0.2 * np.sin(2 * np.pi * 2600 * t + 1.3)
    )
    syl = 0.6 + 0.4 * np.sin(2 * np.pi * 3.2 * t)
    y = y * syl
    burst = (sr * 1.2, sr * 1.45)
    sibs = (0.4 * np.random.RandomState(42).rand(n)) * np.exp(
        -((t - 1.3) ** 2) / (2 * 0.05 ** 2)
    )
    y = y + 0.3 * sibs
    # normalize to -20 dBFS
    y = y / np.max(np.abs(y)) * 0.1
    p = tmp_path / "speechlike.wav"
    sf.write(str(p), y.astype(np.float32), sr, subtype="FLOAT")
    return str(p)
