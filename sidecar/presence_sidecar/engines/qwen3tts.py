"""Qwen3-TTS adapter (12 Hz, 0.6B / 1.7B) — guarded.

Status (2026): Apache-2.0 repo; weight license must be verified in the
registry manifest before enabling (bake-off gate). 3-second voice clone,
natural-language voice design + instruction control (timbre/emotion/prosody),
fine-tuning supported, 3-8 GB VRAM, streaming + non-streaming.

Best fit for the P2 "Expression" panel (Layer B instruction control) and the
P1 fine-tune adapter. The official `qwen-tts` package / HF transformers
integration is imported lazily; without it the engine reports unavailable.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..config import SETTINGS
from .base import (
    BaseEngine, EngineCapabilities, EngineNotAvailable, SynthRequest, SynthResult,
)

MODEL_ID = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
MODEL_VERSION = "1.7B-12Hz"


class Qwen3TTSEngine(BaseEngine):
    id = "qwen3-tts"
    model_id = MODEL_ID
    model_version = MODEL_VERSION

    def __init__(self) -> None:
        self._pipe = None
        self._loaded = False
        self._device = "cpu"

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            supports_reference=True,
            supports_phoneme_inpainting=False,
            supports_seed=True,
            instruction_control=True,   # natural-language voice design
            streaming=True,
            languages=("en", "zh"),
            output_rate=24000,
        )

    def load(self) -> None:
        if self._loaded:
            return
        try:
            from qwen_tts import Qwen3TTSForConditionalGeneration  # type: ignore
        except ImportError:
            try:
                from transformers import Qwen3TTSForConditionalGeneration  # type: ignore
            except ImportError as e:
                raise EngineNotAvailable(
                    "Qwen3-TTS is not installed. pip install -U qwen-tts "
                    "(or a transformers build with the Qwen3-TTS architecture); "
                    "verify the weight license before use."
                ) from e
        self._device = self._pick_device()
        model_dir = SETTINGS.models_dir / "qwen3-tts" / MODEL_VERSION
        if not model_dir.exists():
            from huggingface_hub import snapshot_download
            model_dir.mkdir(parents=True, exist_ok=True)
            snapshot_download(MODEL_ID, local_dir=str(model_dir))
        self._pipe = Qwen3TTSForConditionalGeneration.from_pretrained(
            str(model_dir), torch_dtype="auto"
        ).to(self._device)
        self._pipe.eval()
        self._loaded = True

    def synthesize(self, req: SynthRequest) -> SynthResult:
        if not self._loaded:
            self.load()
        if req.reference is None:
            raise EngineNotAvailable("Qwen3-TTS requires a speaker reference")
        import torch
        if req.seed is not None:
            torch.manual_seed(req.seed)
        # Voice-design / instruction string (Layer B): visible in UI,
        # recorded in provenance. Off by default (None).
        kwargs: dict = {}
        if req.instruct:
            kwargs["instruct"] = req.instruct
        with torch.inference_mode():
            out = self._pipe.generate(
                audio_prompt=req.reference.wav_path,
                text=req.text,
                **kwargs,
            )
        wav = out.wav.cpu().numpy().squeeze().astype(np.float3) if hasattr(out, "wav") else None
        if wav is None:
            raise EngineNotAvailable("Qwen3-TTS returned an unexpected output")
        import hashlib
        out_path = SETTINGS.audio_dir / "gen" / (
            f"qw3-{hashlib.sha256(req.text.encode()).hexdigest()[:12]}.wav"
        )
        self._write_wav(str(out_path), wav, 24000)
        return SynthResult(
            wav_path=str(out_path),
            engine_id=self.id,
            engine_version=f"qwen3-tts-{MODEL_VERSION}",
            model_id=self.model_id,
            model_version=self.model_version,
            seed_used=req.seed,
            warnings=[],
        )
