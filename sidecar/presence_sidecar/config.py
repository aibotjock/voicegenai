"""Runtime paths and settings for the sidecar.

Layout under the data dir (app-data on the host; configurable via
PRESENCE_HOME for tests/CI):

    <home>/
      profiles.db            # SQLite: profiles, scripts, designs, jobs, audit
      audio/                 # encrypted file store (reference windows, generations)
      models/                # model registry cache (manifests + weights)
      exports/               # final exports (WAV/MP3/M4A + sidecar JSON)
      logs/                  # rotating local logs
      keys/                  # dev key fallback (never used when keychain works)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _home() -> Path:
    env = os.environ.get("PRESENCE_HOME")
    if env:
        p = Path(env).expanduser()
    else:
        base = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "data"))
        p = Path(base) / "presence-studio"
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass
class Settings:
    home: Path = field(default_factory=_home)
    # Sidecar security
    host: str = "127.0.0.1"          # never a LAN interface
    port: int = 0                    # 0 -> OS-assigned (token+port passed to app)
    token: str = ""                  # per-launch random bearer token
    # Engine / generation
    default_engine: str = "chatterbox"
    default_design: str = "podcast"
    default_lufs_target: float = -16.0
    true_peak_limit_db: float = -1.5
    master_rate: int = 48000
    master_bits: int = 24
    # Accuracy self-check
    wer_threshold: float = 0.08      # flag segment above this WER
    max_auto_retries: int = 3        # never silently retry past this
    # Models
    model_dir: Path | None = None
    # Job intermediates quota (bytes)
    job_quota_bytes: int = 8 * 1024 * 1024 * 1024

    @property
    def db_path(self) -> Path:
        return self.home / "profiles.db"

    @property
    def audio_dir(self) -> Path:
        p = self.home / "audio"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def models_dir(self) -> Path:
        p = self.model_dir or (self.home / "models")
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def exports_dir(self) -> Path:
        p = self.home / "exports"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def logs_dir(self) -> Path:
        p = self.home / "logs"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def keys_dir(self) -> Path:
        p = self.home / "keys"
        p.mkdir(parents=True, exist_ok=True)
        p.chmod(0o700)
        return p


SETTINGS = Settings()
