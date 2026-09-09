"""Delete-my-voice: full-wipe test asserting ZERO residual bytes (spec §3/§9/§12).

Wipes: embedding, reference audio, adapters, cached generations, DB rows.
The test asserts no residual plaintext or ciphertext for the profile, and
that no voiceprint material can be found in logs/diagnostics exports.
"""
import io
import json
import warnings
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from presence_sidecar import audit
from presence_sidecar.profiles.store import ProfileStore
from presence_sidecar.profiles.keystore import get_master_key


@pytest.fixture()
def store(home, tmp_path, monkeypatch):
    # isolated key: file-backed (CI has no keychain; a warning is expected)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        monkeypatch.setenv("PRESENCE_HOME", str(tmp_path))
        s = ProfileStore()
    yield s


def _ref_bytes(tmp_path) -> bytes:
    sr = 48000
    t = np.arange(sr * 2) / sr
    y = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    p = tmp_path / "ref.wav"
    sf.write(str(p), y, sr, subtype="PCM_24")
    return p.read_bytes()


def test_create_and_roundtrip(store, tmp_path):
    pid = store.create_profile("Me", capture_kind="guided")
    ref = _ref_bytes(tmp_path)
    store.add_reference(pid, "capture", ref, transcript="hello world",
                        duration_s=2.0, snr_db=30.0)
    store.add_embedding(pid, "resemblyzer-0.1",
                        np.zeros(256, dtype=np.float32).tobytes())
    prof = store.get_profile(pid)
    assert prof["status"] == "active"
    assert prof["consent_sha"]
    got = store.load_encrypted(store.get_reference(pid)["file_key"])
    assert got == ref


def test_ciphertext_never_contains_plaintext(store, tmp_path):
    pid = store.create_profile("Me")
    ref = _ref_bytes(tmp_path)
    store.add_reference(pid, "capture", ref, transcript="secret phrase")
    raw = (store.audio_root / store.get_reference(pid)["file_key"]).read_bytes()
    assert ref[:200] not in raw          # audio plaintext must not persist
    assert b"secret phrase" not in raw   # transcript neither


def test_delete_my_voice_zero_residual(store, tmp_path):
    pid = store.create_profile("Me")
    ref = _ref_bytes(tmp_path)
    store.add_reference(pid, "capture", ref, transcript="keep this text")
    store.add_embedding(pid, "resemblyzer-0.1",
                        np.ones(256, dtype=np.float32).tobytes())
    # simulate a cached generation for this profile
    gen_dir = Path(store.home) / "audio" / "gen"
    gen_dir.mkdir(parents=True, exist_ok=True)
    cached = gen_dir / f"{pid}-clip.wav"
    cached.write_bytes(ref)
    res = store.delete_my_voice(pid)
    assert res["ok"], res
    assert res["residual"] == []
    assert not (store.audio_root / pid).exists()
    assert not cached.exists()
    assert store.get_profile(pid) is None
    assert store.get_reference(pid) is None
    assert store.get_embedding(pid) is None
    # nothing left anywhere in the profile tree
    assert not any(store.audio_root.rglob(f"{pid}*"))


def test_delete_nonexistent_profile(store):
    res = store.delete_my_voice("nope")
    assert res["ok"] is False
    assert "not found" in res.get("error", "")


def test_voiceprints_never_in_audit_or_diagnostics(store, tmp_path, home):
    pid = store.create_profile("Me")
    ref = _ref_bytes(tmp_path)
    store.add_reference(pid, "capture", ref, transcript="voiceprint secret")
    audit.append_event("generate", profile_id=pid,
                       text_sha256="0" * 64, detail="text never logged")
    log_path = Path(home.logs_dir) / "audit.jsonl"
    logs = log_path.read_text()
    assert "voiceprint secret" not in logs       # no transcripts
    assert "keep this text" not in logs         # no script content
    bundle = audit.diagnostics_bundle()
    assert "voiceprint secret" not in bundle
    assert "No audio, no voiceprints" in bundle
    events = audit.read_events()
    assert all("voiceprint secret" not in json.dumps(e) for e in events)
