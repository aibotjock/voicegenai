"""Local audit log: generation + export events.

Records timestamps, durations, engine, design id, and text SHA-256 — never
text content, never audio. Rotating local logs; a diagnostics export
includes logs + config only (no audio, no voiceprints).
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

from .config import SETTINGS


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def append_event(
    kind: str,
    profile_id: str | None = None,
    design_id: str | None = None,
    engine_id: str | None = None,
    text_sha256: str | None = None,
    duration_s: float | None = None,
    detail: str | None = None,
) -> dict:
    event = {
        "ts": _now(),
        "event": kind,
        "profile_id": profile_id,
        "design_id": design_id,
        "engine_id": engine_id,
        "text_sha256": text_sha256,
        "duration_s": round(duration_s, 2) if duration_s is not None else None,
        "detail": detail,
    }
    path = SETTINGS.logs_dir / "audit.jsonl"
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")
    return event


def read_events(limit: int = 200) -> list[dict]:
    path = SETTINGS.logs_dir / "audit.jsonl"
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def diagnostics_bundle() -> str:
    """Logs + config, no audio, no voiceprints. Returns the JSON payload."""
    logs: dict[str, str] = {}
    for p in sorted(SETTINGS.logs_dir.glob("*.jsonl")):
        text = p.read_text(encoding="utf-8")
        if len(text) > 200_000:
            text = text[-200_000:]
        logs[p.name] = text
    return json.dumps(
        {
            "app": "Presence Studio",
            "generated_at": _now(),
            "config": {
                "default_engine": SETTINGS.default_engine,
                "default_design": SETTINGS.default_design,
                "home": str(SETTINGS.home),
            },
            "logs": logs,
            "note": "Diagnostics bundle: logs and config only. No audio, "
                    "no voiceprints, no script content.",
        },
        indent=2,
    )
