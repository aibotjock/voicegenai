"""Presence Studio sidecar.

Single-process Python sidecar that owns TTS synthesis, the DSP voice-design
chain, the accuracy self-check (WER), and export with provenance.
Local-first: binds 127.0.0.1 only, per-launch random bearer token.
"""

__version__ = "0.1.0"

APP_NAME = "Presence Studio"
APP_VERSION = "0.1.0"

# Provenance flag: every export is explicitly marked synthetic audio.
SYNTHETIC_FLAG = "synthetic-audio"
