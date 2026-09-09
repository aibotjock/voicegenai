"""Consent: mandatory plain-English flow at first capture.

The consent record is stored with the profile (hash of the exact copy shown,
timestamp). Copy is reviewed before ship (docs/consent-ethics.md).
"""
from __future__ import annotations

import datetime as _dt
import hashlib

CONSENT_VERSION = "1.0"

CONSENT_TEXT = f"""
You are about to clone your own voice.

What happens:
- We record the sentences you read and build a private voice profile: a
  voiceprint (a mathematical fingerprint of your voice), a short reference
  clip, and the text you read.
- Everything stays on this computer. No audio or voiceprint is ever sent to
  a server, included in telemetry, crash reports, or diagnostics.

Where it lives:
- Your profile is stored in an encrypted folder on this machine, locked with
  a key kept in your operating system's secure key storage.

Your rights:
- You can delete your voice at any time, in one click. Deletion removes the
  voiceprint, reference audio, fine-tuning adapters, and generated audio.
- This tool is for your own voice, for your own presentations. Using it to
  impersonate someone else or to deceive is not allowed.
- Where disclosure is the norm (podcasts, webinars, recorded training), we
  encourage you to tell your audience that audio was produced with your
  cloned voice.
""".strip()


def consent_sha() -> str:
    return hashlib.sha256(f"{CONSENT_TEXT}|{CONSENT_VERSION}".encode()).hexdigest()


def consent_record() -> dict:
    return {
        "version": CONSENT_VERSION,
        "text_sha256": consent_sha(),
        "recorded_at": _dt.datetime.now(_dt.timezone.utc).isoformat(
            timespec="seconds"
        ),
    }
