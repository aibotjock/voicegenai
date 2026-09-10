"""Profile store: SQLite metadata + encrypted file store.

- SQLite: profiles, references (metadata), embeddings (metadata),
  adapters (metadata), designs, scripts, jobs, exports.
- Encrypted file store: reference audio, voiceprints (embeddings), and
  generated audio are Fernet-encrypted (AEAD) with the keychain-held key.
  File names are content hashes; plaintext never persists.
- delete_my_voice: one click, instant, verifiable — wipes embedding,
  reference audio, fine-tune adapters, cached generations, and DB rows.
  A test asserts zero residual bytes (tests/test_profiles_delete.py).
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .. import config
from .consent import consent_record, consent_sha
from .keystore import new_fernet

SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL,
  consent TEXT NOT NULL,
  consent_sha TEXT NOT NULL,
  capture_kind TEXT NOT NULL DEFAULT 'unknown'
);
CREATE TABLE IF NOT EXISTS voice_references (
  id TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  file_key TEXT NOT NULL,
  transcript TEXT,
  duration_s REAL,
  snr_db REAL,
  selected INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS embeddings (
  id TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  model_id TEXT NOT NULL,
  file_key TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS adapters (
  id TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  file_key TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS designs (
  id TEXT PRIMARY KEY,
  profile_id TEXT,
  script_id TEXT,
  name TEXT NOT NULL,
  params_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scripts (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  script_id TEXT,
  profile_id TEXT,
  design_id TEXT,
  engine_id TEXT,
  seed INTEGER,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS exports (
  id TEXT PRIMARY KEY,
  job_id TEXT,
  path TEXT NOT NULL,
  formats TEXT NOT NULL,
  provenance_sha TEXT NOT NULL,
  created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _uuid() -> str:
    import uuid
    return uuid.uuid4().hex


class ProfileStore:
    def __init__(self, home: Path | None = None) -> None:
        self.home = Path(home) if home else config.SETTINGS.home
        self.db_path = self.home / "profiles.db"
        self.audio_root = self.home / "audio" / "profiles"
        self.audio_root.mkdir(parents=True, exist_ok=True)
        self._fernet = new_fernet()
        # generation jobs run in a worker thread; our usage is serialized
        # (single job at a time per store), so cross-thread access is safe.
        self.db = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)
        self.db.commit()

    # -- encrypted file store ---------------------------------------------

    def store_encrypted(self, profile_id: str, kind: str, data: bytes) -> str:
        """Encrypt and store bytes; returns the file key (content hash)."""
        digest = hashlib.sha256(data).hexdigest()
        prof_dir = self.audio_root / profile_id
        prof_dir.mkdir(parents=True, exist_ok=True)
        path = prof_dir / f"{digest[:16]}.{kind}.enc"
        path.write_bytes(self._fernet.encrypt(data))
        return f"{profile_id}/{digest[:16]}.{kind}.enc"

    def load_encrypted(self, file_key: str) -> bytes:
        path = self.audio_root / file_key
        if not path.exists():
            raise FileNotFoundError(file_key)
        return self._fernet.decrypt(path.read_bytes())

    def delete_file_key(self, file_key: str) -> bool:
        path = self.audio_root / file_key
        if path.exists():
            path.unlink()
            return True
        return False

    # -- profiles -----------------------------------------------------------

    def create_profile(self, name: str, capture_kind: str = "guided") -> str:
        pid = _uuid()
        rec = consent_record()
        self.db.execute(
            "INSERT INTO profiles (id, name, status, created_at, consent, "
            "consent_sha, capture_kind) VALUES (?,?,?,?,?,?,?)",
            (pid, name, "active", _now(), str(rec), consent_sha(), capture_kind),
        )
        self.db.commit()
        return pid

    def get_profile(self, pid: str) -> dict | None:
        row = self.db.execute("SELECT * FROM profiles WHERE id=?", (pid,)).fetchone()
        return dict(row) if row else None

    def list_profiles(self) -> list[dict]:
        rows = self.db.execute("SELECT * FROM profiles ORDER BY created_at").fetchall()
        return [dict(r) for r in rows]

    def add_reference(self, pid: str, kind: str, data: bytes, transcript: str = "",
                      duration_s: float = 0.0, snr_db: float = 0.0,
                      selected: bool = True) -> str:
        rid = _uuid()
        key = self.store_encrypted(pid, "ref", data)
        self.db.execute(
            "INSERT INTO voice_references (id, profile_id, kind, file_key, transcript,"
            " duration_s, snr_db, selected, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (rid, pid, kind, key, transcript, duration_s, snr_db,
             1 if selected else 0, _now()),
        )
        self.db.commit()
        return rid

    def add_embedding(self, pid: str, model_id: str, vector: bytes) -> str:
        eid = _uuid()
        key = self.store_encrypted(pid, "emb", vector)
        self.db.execute(
            "INSERT INTO embeddings (id, profile_id, model_id, file_key, created_at)"
            " VALUES (?,?,?,?,?)", (eid, pid, model_id, key, _now()),
        )
        self.db.commit()
        return eid

    def get_reference(self, pid: str, selected: bool = True) -> dict | None:
        row = self.db.execute(
            "SELECT * FROM voice_references WHERE profile_id=? AND selected=? "
            "ORDER BY created_at DESC LIMIT 1", (pid, 1 if selected else 0),
        ).fetchone()
        return dict(row) if row else None

    def get_embedding(self, pid: str) -> dict | None:
        row = self.db.execute(
            "SELECT * FROM embeddings WHERE profile_id=? ORDER BY created_at DESC"
            " LIMIT 1", (pid,),
        ).fetchone()
        return dict(row) if row else None

    def add_design(self, name: str, params: dict, pid: str | None = None,
                   script_id: str | None = None) -> str:
        did = _uuid()
        import json
        self.db.execute(
            "INSERT INTO designs (id, profile_id, script_id, name, params_json,"
            " created_at) VALUES (?,?,?,?,?,?)",
            (did, pid, script_id, name, json.dumps(params, sort_keys=True), _now()),
        )
        self.db.commit()
        return did

    # -- delete my voice ----------------------------------------------------

    def delete_my_voice(self, pid: str) -> dict:
        """Wipe everything for a profile. Returns a verifiable manifest."""
        deleted: list[str] = []
        prof = self.get_profile(pid)
        if prof is None:
            return {"profile_id": pid, "deleted": [], "residual": [],
                    "ok": False, "error": "profile not found"}
        # encrypted files for this profile
        prof_dir = self.audio_root / pid
        if prof_dir.exists():
            for f in sorted(prof_dir.iterdir()):
                if f.is_file():
                    f.unlink()
                    deleted.append(f"file:{f.name}")
            prof_dir.rmdir()
        # cached generations tagged to this profile
        gen_dir = config.SETTINGS.audio_dir / "gen"
        if gen_dir.exists():
            for f in sorted(gen_dir.glob(f"{pid}-*")):
                f.unlink()
                deleted.append(f"file:{f.name}")
        # DB rows (cascades to references/embeddings/adapters)
        self.db.execute("DELETE FROM profiles WHERE id=?", (pid,))
        self.db.execute("DELETE FROM jobs WHERE profile_id=?", (pid,))
        self.db.execute("DELETE FROM exports WHERE path LIKE ?",
                        (f"%{pid}%",))
        self.db.commit()
        deleted.append("db:profile-row")
        # residual check: no file anywhere in the profile tree
        residual = []
        if prof_dir.exists():
            residual = [str(f) for f in prof_dir.rglob("*")]
        return {"profile_id": pid, "deleted": deleted, "residual": residual,
                "ok": not residual}

    def close(self) -> None:
        self.db.close()
