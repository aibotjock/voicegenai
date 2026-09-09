# Presence Studio

Professional voice clone & voice-design desktop app (local-first).

Clone your own voice once, generate speech from any script, and apply
professional "voice design" (pitch, formant, pace, EQ, dynamics, loudness)
to produce presentation-ready audio — broadcast-clean, verbatim, and
provably synthetic.

> **Status: M0 core under construction.** The Python sidecar (text pipeline,
> DSP chain, engine adapters, WER self-check, provenance export, profile
> store) is in this repo. The Tauri/React shell, capture UX, and CI land in
> the next milestone.

## What's here

```
sidecar/presence_sidecar/
  text_pipeline/   deterministic spoken-form normalization, glossary (ARPAbet
                   + say-as), prosody markup, segmentation
  dsp/             fixed-order Layer-A chain: Rubber Band pitch/formant (lock),
                   5-band EQ, compressor w/ auto makeup, Python band-split
                   de-ess, two-pass EBU R128 loudnorm + pyloudnorm verify,
                   finalize (TP guard, DC removal, padding, 48k/24-bit)
  engines/         engine contract + adapters: chatterbox (default),
                   cosyvoice3 (guarded), qwen3-tts (guarded), offline-stub
                   (pipeline test only)
  asr/             faster-whisper local ASR + WER self-check (flag > 8%,
                   max 3 auto-retries, never silent)
  identity/        speaker similarity (SECS) + verification gates
  naturalness/     UTMOS (no-reference MOS)
  export/          WAV/MP3/M4A with provenance always embedded + sidecar JSON
  profiles/        SQLite + Fernet-encrypted file store, keychain-held key,
                   consent records, verifiable "Delete my voice"
  models/          versioned model registry w/ checksum verification
  audit.py         local audit log (hashes only, never text/audio)
tests/             unit tests (numbers, normalization table, ...)
```

## Quickstart (sidecar)

```bash
python3 -m venv .venv
.venv/bin/pip install -e .           # core
.venv/bin/pip install -e .[ml]       # + torch, faster-whisper, utmos-pytorch, resemblyzer
# CUDA torch (Linux):
.venv/bin/pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu128

# generate (offline-stub engine, no weights — pipeline validation):
PRESENCE_HOME=~/.local/data/presence-studio \
  .venv/bin/presence generate "Hello, this is a test." --engine offline-stub --out /tmp/t.wav

# run tests:
.venv/bin/python -m pytest tests/ -q
```

## Hardware

| Tier | Specs | Notes |
|---|---|---|
| Recommended | 8 GB VRAM / 16 GB RAM / 10 GB disk | 0.5B-class engines, ≥5× realtime |
| Minimum | 6 GB VRAM | slower but full-featured |
| CPU-only | 16 GB RAM | functional; UI states expected time before generation |

Models are opt-in downloads with size + license shown; never committed.

## Non-negotiables (see build prompt §9)

- Self-voice only; uploaded audio must pass voiceprint match.
- All voice data stays on-device; zero egress in local mode (CI-enforced).
- Every export is marked synthetic with full provenance (no toggle).
- "Delete my voice" is one click, instant, test-verified to zero residual.

## Layout (planned)

- `app/` — Tauri v2 + React + TypeScript shell (Studio / Compose / Library)
- `docs/` — text-normalization table, engine scorecard, license audit,
  consent copy, quality harness results
- `eval/` — fixed 50-sentence eval script + reference manifest
