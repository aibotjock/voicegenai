"""Chatterbox engine adapter (Resemble AI).

Status (2026): Apache-2.0 code; weight license verified in the model
registry manifest (docs/license-audit.md). English only. No instruction
control (Layer B not available on this engine). No phoneme inpainting —
glossary entries fall back to say-as / letter form.

API (chatterbox-tts 0.1.x):
    tts = ChatterboxTTS.from_local(ckpt_dir, device)
    tts.prepare_conditionals(ref_wav_path, exaggeration=0.5)
    wav = tts.generate(text, temperature=0.8)   # [1, samples] @ 24 kHz

The engine applies its own inaudible watermark (Perth) to output.
Determinism: seed via torch.manual_seed before each call; reproducible
within the same runtime environment (CUDA non-determinism: documented).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from ..config import SETTINGS
from .base import (
    BaseEngine, EngineCapabilities, EngineNotAvailable, SynthRequest, SynthResult,
)

MODEL_REPO = "ResembleAI/chatterbox"
MODEL_VERSION = "2025.08.18"  # pinned in registry manifest; re-audit on bump


def _chatterbox_version() -> str:
    try:
        from importlib.metadata import version
        return version("chatterbox-tts")
    except Exception:
        return "unknown"


class ChatterboxEngine(BaseEngine):
    id = "chatterbox"
    model_id = MODEL_REPO
    model_version = MODEL_VERSION

    def __init__(self) -> None:
        self._tts = None
        self._loaded = False
        self._ckpt_dir: Path | None = None
        self._device: str = "cpu"

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            supports_reference=True,
            supports_phoneme_inpainting=False,
            supports_seed=True,
            instruction_control=False,
            streaming=False,
            languages=("en",),
            output_rate=24000,
        )

    def _resolve_ckpt(self) -> Path:
        """Use the registry cache when present (checksum-verified at download)."""
        cached = SETTINGS.models_dir / "chatterbox" / MODEL_VERSION
        if (cached / "ve.safetensors").exists():
            return cached
        from huggingface_hub import snapshot_download
        cached.mkdir(parents=True, exist_ok=True)
        snapshot_download(
            MODEL_REPO, local_dir=str(cached),
            allow_patterns=["*.safetensors", "*.json", "conds.pt", "*.md"],
        )
        self._ckpt_dir = cached
        return cached

    def load(self) -> None:
        if self._loaded:
            return
        try:
            from chatterbox import ChatterboxTTS
        except ImportError as e:
            raise EngineNotAvailable(
                "chatterbox-tts is not installed in the sidecar environment"
            ) from e
        self._device = self._pick_device()
        ckpt = self._resolve_ckpt()
        self._tts = ChatterboxTTS.from_local(ckpt, self._device)
        self._loaded = True

    def synthesize(self, req: SynthRequest) -> SynthResult:
        if not self._loaded:
            self.load()
        if req.reference is None:
            raise EngineNotAvailable(
                "Chatterbox requires a verified speaker reference"
            )
        if req.instruct:
            # no instruction control on this engine; visible to the user
            pass
        import torch
        warnings: list[str] = []
        if req.glossary_spans:
            warnings.append(
                "Chatterbox has no phoneme inpainting; "
                f"{len(req.glossary_spans)} glossary span(s) read normally"
            )
        # seed for reproducible sampling within the same runtime environment
        if req.seed is not None:
            torch.manual_seed(req.seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(req.seed)

        self._tts.prepare_conditionals(
            req.reference.wav_path, exaggeration=0.5
        )
        wav = self._tts.generate(req.text, temperature=0.8)
        wav = wav.squeeze(0).detach().cpu().numpy().astype(np.float32)
        out = SETTINGS.audio_dir / "gen" / (
            f"cbx-{hashlib.sha256(req.text.encode()).hexdigest()[:12]}.wav"
        )
        self._write_wav(str(out), wav, self._tts.sr)
        return SynthResult(
            wav_path=str(out),
            engine_id=self.id,
            engine_version=_chatterbox_version(),
            model_id=self.model_id,
            model_version=self.model_version,
            seed_used=req.seed,
            warnings=warnings,
        )
