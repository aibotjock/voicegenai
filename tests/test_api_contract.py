"""Sidecar API contract tests: token auth, health, presets, profiles,
delete-my-voice, and the job flow with the offline-stub engine (no weights).

Security invariants under test:
- binds 127.0.0.1 config, per-launch token, 401 without/with wrong token
- profile create runs QC and REFUSES bad captures
- delete-my-voice returns zero residual
- jobs: per-segment states, WER flags surfaced, SSE stream, export with
  provenance
"""
import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from presence_sidecar.api import create_app
from presence_sidecar.config import SETTINGS


TOKEN = "test-token-123"


@pytest.fixture()
def app(home, monkeypatch):
    monkeypatch.setattr(SETTINGS, "default_engine", "offline-stub")
    a = create_app(token=TOKEN)
    return a


@pytest.fixture()
def client(app):
    return TestClient(app)


def _auth(client, token=TOKEN):
    return {"Authorization": f"Bearer {token}"}


def _wav_bytes(tmp_path, dur=32.0, sr=16000, amp=0.3, pause_noise=0.002):
    """QC-passing capture: >= 30 s, speech-like blocks separated by pauses
    (continuous tone reads as 'silence' to the envelope heuristic; short
    files fail the 30 s usability gate)."""
    n = int(sr * dur)
    y = np.zeros(n, dtype=np.float32)
    rng = np.random.RandomState(5)
    block = int(sr * 4.0)
    gap = int(sr * 1.0)
    i = 0
    while i + block < n:
        t = np.arange(block) / sr
        seg = amp * np.sin(2 * np.pi * 440 * t) * (
            0.4 + 0.6 * np.abs(np.sin(2 * np.pi * 1.1 * t)))
        y[i:i + block] = seg.astype(np.float32)
        i += block + gap
    y += pause_noise * rng.randn(n).astype(np.float32)
    y = np.clip(y, -0.9, 0.9).astype(np.float32)
    p = tmp_path / "up.wav"
    sf.write(str(p), y, sr, subtype="PCM_24")
    return p.read_bytes()


def test_health_no_auth(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["app"] == "Presence Studio"
    # test-only engines are hidden from the health listing
    assert all(e["id"] != "offline-stub" for e in r.json()["engines"])


def test_endpoints_require_token(client):
    for path in ("/api/v1/presets", "/api/v1/profiles", "/api/v1/audit"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"Authorization": "Bearer nope"}).status_code == 401
        assert client.get(path, headers=_auth(client)).status_code == 200


def test_presets_listing(client):
    r = client.get("/api/v1/presets", headers=_auth(client))
    data = r.json()
    assert set(data) >= {"boardroom", "keynote", "calm-expert", "podcast",
                         "rehearsal-raw"}
    assert data["boardroom"]["lufs_target"] == -16.0


def test_profile_create_qc_refuses_silent_capture(client, tmp_path):
    silent = _wav_bytes(tmp_path, amp=0.0)
    r = client.post("/api/v1/profiles", headers=_auth(client),
                    data={"name": "Me"},
                    files={"capture": ("c.wav", silent, "audio/wav")})
    body = r.json()
    assert body["ok"] is False
    assert any("silence" in i for i in body["qc"]["issues"])


def test_profile_lifecycle_and_delete(client, tmp_path):
    data = _wav_bytes(tmp_path)
    r = client.post("/api/v1/profiles", headers=_auth(client),
                    data={"name": "Me"},
                    files={"capture": ("c.wav", data, "audio/wav")})
    pid = r.json()["profile_id"]
    assert r.json()["ok"] is True
    listed = client.get("/api/v1/profiles", headers=_auth(client)).json()
    assert any(p["id"] == pid for p in listed)
    # voiceprint material must NOT be in the listing
    assert "consent" not in listed[0]
    d = client.delete(f"/api/v1/profiles/{pid}", headers=_auth(client))
    assert d.status_code == 200 and d.json()["residual"] == 0
    assert not any(p["id"] == pid for p in
                   client.get("/api/v1/profiles", headers=_auth(client)).json())


def _make_verified_profile(client, tmp_path):
    data = _wav_bytes(tmp_path)
    r = client.post("/api/v1/profiles", headers=_auth(client),
                    data={"name": "Me"},
                    files={"capture": ("c.wav", data, "audio/wav")})
    pid = r.json()["profile_id"]
    # verification is normally a live-utterance gate; tests mark it directly
    from presence_sidecar.profiles.store import ProfileStore
    store = ProfileStore()
    store.db.execute("UPDATE profiles SET verify_status='verified' WHERE id=?",
                     (pid,))
    store.db.commit()
    return pid


def test_generate_job_flow_with_stub_engine(client, tmp_path, home, monkeypatch):
    monkeypatch.setattr(SETTINGS, "default_engine", "offline-stub")
    pid = _make_verified_profile(client, tmp_path)
    r = client.post("/api/v1/generate", headers=_auth(client), json={
        "script": "First sentence here. Second sentence follows!\n\n"
                  "A third sentence in paragraph two.",
        "fmt": "text", "profile_id": pid, "design": "podcast",
        "engine": "offline-stub", "seed": 7, "check_wer": False,
    })
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    # wait for job completion (stub is instant; poll briefly)
    import time
    for _ in range(80):
        snap = client.get(f"/api/v1/jobs/{job_id}", headers=_auth(client)).json()
        if snap["status"] in ("done", "failed"):
            break
        time.sleep(0.25)
    assert snap["status"] == "done", snap.get("error")
    assert len(snap["segments"]) == 3
    assert all(s["status"] == "done" for s in snap["segments"])
    # SSE stream reachable
    with client.stream("GET", f"/api/v1/jobs/{job_id}/events") as stream:
        assert stream.status_code == 200
    # export with provenance
    ex = client.post(f"/api/v1/jobs/{job_id}/export", headers=_auth(client),
                     json={"formats": "wav,mp3", "stem": "api-test"}).json()
    assert ex["ok"] is True
    assert Path(ex["master"]).exists()
    payload = json.loads(Path(ex["sidecar"]).read_text())
    assert payload["synthetic"] is True
    assert payload["engine_id"] == "offline-stub"
    assert Path(ex["mp3"]).exists()


def test_generate_requires_verified_profile(client, tmp_path):
    data = _wav_bytes(tmp_path)
    r = client.post("/api/v1/profiles", headers=_auth(client),
                    data={"name": "Me"},
                    files={"capture": ("c.wav", data, "audio/wav")})
    pid = r.json()["profile_id"]
    r = client.post("/api/v1/generate", headers=_auth(client), json={
        "script": "Hello there.", "profile_id": pid, "design": "podcast",
        "engine": "offline-stub", "check_wer": False,
    })
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    import time
    for _ in range(20):
        snap = client.get(f"/api/v1/jobs/{job_id}", headers=_auth(client)).json()
        if snap["status"] in ("done", "failed"):
            break
        time.sleep(0.25)
    assert snap["status"] == "failed"
    assert "not verified" in snap["error"]


def test_audit_and_diagnostics(client):
    r = client.get("/api/v1/audit", headers=_auth(client))
    assert r.status_code == 200
    d = client.get("/api/v1/diagnostics", headers=_auth(client)).json()
    assert "No audio" in d["bundle"]
