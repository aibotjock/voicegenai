"""Deterministic offline engine (no weights).

Purpose: validate the full pipeline (text -> synthesis slot -> WER interface
-> DSP -> export -> provenance) without any model download. It emits a
deterministic tone per sentence (frequency seeded by text hash), which is
NOT speech — the WER self-check is explicitly skipped for this engine and the
UI flags it as a test-only engine. Never a default.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np

from .base import BaseEngine, EngineCapabilities, EngineRef, SynthRequest, SynthResult


class StubEngine(BaseEngine):
    id = "offline-stub"
    model_id = "none"
    model_version = "0.0.0"
    output_rate = 48000

    def __init__(self, outdir: str | Path = ".") -> None:
        self.outdir = Path(outdir)
        self._loaded = False

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            supports_reference=False,
            supports_phoneme_inpainting=False,
            supports_seed=True,
            output_rate=self.output_rate,
            languages=("test",),
        )

    def load(self) -> None:
        self._loaded = True

    def synthesize(self, req: SynthRequest) -> SynthResult:
        h = hashlib.sha256(req.text.encode()).hexdigest()
        freq = 180.0 + 140.0 * (int(h[:8], 16) % 1000) / 1000.0
        dur = 0.6 + 0.004 * min(len(req.text), 120)
        sr = self.output_rate
        n = int(dur * sr)
        t = np.arange(n) / sr
        # two harmonics + gentle AM + fades: deterministic, stable, distinct
        tone = (
            0.7 * np.sin(2 * math.pi * freq * t)
            + 0.3 * np.sin(2 * math.pi * freq * 2 * t)
        ) * (0.8 + 0.2 * np.sin(2 * math.pi * 3.0 * t))
        fade = int(0.01 * sr)
        tone[:fade] *= np.linspace(0, 1, fade)
        tone[-fade:] *= np.linspace(1, 0, fade)
        tone = (0.5 * tone).astype(np.float32)
        out = self.outdir / f"stub-{h[:12]}.wav"
        self._write_wav(str(out), tone, sr)
        return SynthResult(
            wav_path=str(out),
            engine_id=self.id,
            engine_version="0.0.0",
            model_id=self.model_id,
            model_version=self.model_version,
            seed_used=req.seed,
            warnings=["offline-stub: pipeline-test engine, output is NOT speech"],
        )
