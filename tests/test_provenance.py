"""Provenance-on-100%-of-exports tests (spec §8) + sidecar + loudness report."""
import json
import struct
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from presence_sidecar.dsp import PRESETS
from presence_sidecar.export.provenance import (
    Provenance, embed_wav, embed_mp3, embed_m4a, write_sidecar,
)
from presence_sidecar.export.writer import export, loudness_report_text


@pytest.fixture()
def clip(tmp_path):
    sr = 48000
    t = np.arange(sr * 2) / sr
    y = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    p = tmp_path / "clip.wav"
    sf.write(str(p), y, sr, subtype="PCM_24")
    return str(p)


def make_prov() -> Provenance:
    return Provenance(
        engine_id="chatterbox", engine_version="0.1.7",
        model_id="ResembleAI/chatterbox", model_version="2025.08.18",
        design_id="boardroom", design_name="Boardroom",
        design_params_hash=PRESETS["boardroom"].params_hash(),
        seed=1234, script_sha256="ab" * 32,
        loudness={"integrated_lufs": -16.05, "true_peak_db": -1.87,
                  "lra_lu": 1.68},
    )


@pytest.mark.parametrize("formats", [("wav",), ("wav", "mp3"), ("wav", "m4a"),
                                     ("wav", "mp3", "m4a")])
def test_provenance_on_every_export(tmp_path, clip, formats):
    """P0: provenance is embedded in 100% of exports, no toggle."""
    ex = export(clip, str(tmp_path / "out"), make_prov(),
                formats=formats, stem="t")
    written = [ex.master_wav, ex.mp3, ex.m4a]
    written = [w for w in written if w]
    assert len(written) == len(formats)
    for w in written:
        assert Path(w).exists()
    data = Path(ex.master_wav).read_bytes()
    assert b"PSYN" in data
    payload = json.loads(_read_psyn(data))
    assert payload["synthetic"] is True
    assert payload["engine_id"] == "chatterbox"
    assert payload["seed"] == 1234
    assert payload["design_params_hash"] == PRESETS["boardroom"].params_hash()
    # sidecar JSON always present
    side = json.loads(Path(ex.sidecar).read_text())
    assert side["synthetic_flag"] == "synthetic-audio"


def _read_psyn(data: bytes) -> bytes:
    i = data.find(b"PSYN")
    size = struct.unpack("<I", data[i + 4:i + 8])[0]
    return data[i + 8:i + 8 + size]


def test_mp3_and_m4a_tags(tmp_path, clip):
    ex = export(clip, str(tmp_path / "out"), make_prov(),
                formats=("wav", "mp3", "m4a"), stem="t")
    from mutagen.id3 import ID3
    tags = ID3(ex.mp3)
    assert any(k.startswith("TXXX:presence-provenance") for k in tags.keys())
    from mutagen.mp4 import MP4
    m4 = MP4(ex.m4a)
    prov = json.loads(m4["----:com.presence.studio:provenance"][0].decode())
    assert prov["engine_id"] == "chatterbox"
    assert prov["synthetic"] is True


def test_loudness_report_written(tmp_path, clip):
    ex = export(clip, str(tmp_path / "out"), make_prov(), formats=("wav",),
                stem="t")
    report = Path(ex.master_wav).parent / "t.loudness.txt"
    assert report.exists()
    text = report.read_text()
    assert "-16.05 LUFS" in text
    assert "BS.1770-4" in text


def test_provenance_is_json_stable_and_hashable():
    p = make_prov()
    assert p.params_hash() == make_prov().params_hash()
    d = p.to_dict()
    assert d["app"] == "Presence Studio"
    assert "generated_at" in d
