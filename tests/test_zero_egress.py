"""Zero-egress test (spec §9/§12): in local mode NOTHING makes a network
connection. We hard-block socket connects, run the full local flow
(profile -> generate (stub engine) -> export), and assert zero attempts.
In CI the same test runs with network egress fully blocked; any connection
attempt fails the build.
"""
import socket
import threading
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

ATTEMPTS: list = []


_REAL_CONNECT = socket.socket.connect
_REAL_CONNECT_EX = socket.socket.connect_ex


@pytest.fixture()
def blocked_sockets(monkeypatch):
    """Block network egress (AF_INET/AF_INET6). AF_UNIX stays allowed: the
    OS keychain (DBus/Secret Service) is local IPC, not network egress —
    the zero-egress contract forbids sending data to the network, not using
    the local secure key store."""
    ATTEMPTS.clear()

    def guarded_connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            ATTEMPTS.append(address)
            raise AssertionError(
                f"network egress attempt in local mode: {address}")
        return _REAL_CONNECT(self, address)

    def guarded_connect_ex(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            ATTEMPTS.append(address)
            return 1
        return _REAL_CONNECT_EX(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    yield ATTEMPTS
    ATTEMPTS.clear()


def test_local_flow_makes_zero_network_calls(blocked_sockets, tmp_path, home):
    from presence_sidecar.profiles.store import ProfileStore
    from presence_sidecar.jobs.manager import GenerationJob

    # profile store + encrypted file write (all local)
    store = ProfileStore()
    pid = store.create_profile("Me", capture_kind="guided")
    sr = 16000
    n = sr * 32
    ref = np.zeros(n, dtype=np.float32)
    rng = np.random.RandomState(1)
    block, gap = sr * 4, sr
    i = 0
    while i + block < n:
        t = np.arange(block) / sr
        ref[i:i + block] = (0.3 * np.sin(2 * np.pi * 440 * t)
                            * (0.4 + 0.6 * np.abs(np.sin(2 * np.pi * 1.1 * t))))
        i += block + gap
    ref = (ref + 0.002 * rng.randn(n)).astype(np.float32)
    p = tmp_path / "ref.wav"
    sf.write(str(p), ref, sr, subtype="PCM_24")
    ref_bytes = p.read_bytes()
    store.add_reference(pid, "capture", ref_bytes, transcript="hi",
                        duration_s=2.0, snr_db=30.0)
    store.db.execute("UPDATE profiles SET verify_status='verified' WHERE id=?",
                     (pid,))
    store.db.commit()

    # generation job on the offline-stub engine (no weights, no network)
    job = GenerationJob({
        "script": "Zero egress test sentence one. Sentence two here.",
        "fmt": "text", "profile_id": pid, "design": "podcast",
        "engine": "offline-stub", "seed": 3, "check_wer": False,
    }, store)
    job.start()
    job._thread.join(timeout=30)
    assert job.status == "done", job.error
    out = job.export(formats="wav", stem="zero-egress-test")
    assert Path(out["master"]).exists()
    assert out["provenance"]["synthetic"] is True

    store.delete_my_voice(pid)
    assert blocked_sockets == [], f"connection attempts: {blocked_sockets}"


def test_socket_guard_actually_blocks(blocked_sockets):
    # sanity: the guard must catch a real internet connect attempt
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(("8.8.8.8", 53))
    except AssertionError:
        pass
    assert ATTEMPTS, "guard did not fire"
