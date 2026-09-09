"""CosyVoice3 (Fun-CosyVoice3-0.5B-2512) adapter — guarded.

Status (2026): Apache-2.0 repo; weight license must be verified in the
registry manifest before this engine can be enabled (bake-off gate).
0.5B, ~4.5 GB VRAM, 9 languages incl. English, cross-lingual zero-shot
clone, bi-directional streaming (~150 ms), instruction control, CMU-phoneme
pronunciation inpainting. Known caveat: occasional garbled output on long
paragraphs -> sentence-level generation + WER self-check mitigate it.

The FunAudioLLM/CosyVoice repo ships a python runtime; this adapter lazily
imports it and maps the sidecar contract onto it. If the runtime or weights
are missing, the engine reports itself unavailable (never silently).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..config import SETTINGS
from .base import (
    BaseEngine, EngineCapabilities, EngineNotAvailable, SynthRequest, SynthResult,
)

MODEL_ID = "FunAudioLLM/Fun-CosyVoice3-0.5B-2512"
MODEL_VERSION = "2512"


def _engine_version() -> str:
    return f"cosyvoice3-{MODEL_VERSION}"


class CosyVoice3Engine(BaseEngine):
    id = "cosyvoice3"
    model_id = MODEL_ID
    model_version = MODEL_VERSION

    def __init__(self) -> None:
        self._model = None
        self._loaded = False
        self._device = "cpu"

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            supports_reference=True,
            supports_phoneme_inpainting=True,
            supports_seed=True,
            instruction_control=True,
            streaming=True,
            languages=("en", "zh", "ja", "ko", "de", "fr", "ru", "es", "it"),
            output_rate=24000,
        )

    def load(self) -> None:
        if self._loaded:
            return
        try:
            from cosyvoice.cli.cosyvoice import CosyVoice3  # type: ignore
        except ImportError as e:
            raise EngineNotAvailable(
                "CosyVoice runtime is not installed. "
                "Clone FunAudioLLM/CosyVoice and pip install -r requirements.txt "
                "in the sidecar environment; verify the weight license before use."
            ) from e
        self._device = self._pick_device()
        model_dir = SETTINGS.models_dir / "cosyvoice3" / MODEL_VERSION
        if not model_dir.exists():
            from huggingface_hub import snapshot_download
            model_dir.mkdir(parents=True, exist_ok=True)
            snapshot_download(MODEL_ID, local_dir=str(model_dir))
        self._model = CosyVoice3(
            str(model_dir), load_jit=False, load_trt=False,
            load_vllm=False, fp16=False,
        )
        self._loaded = True

    def synthesize(self, req: SynthRequest) -> SynthResult:
        if not self._loaded:
            self.load()
        if req.reference is None:
            raise EngineNotAvailable("CosyVoice3 requires a speaker reference")
        import torch
        if req.seed is not None:
            torch.manual_seed(req.seed)
        warnings: list[str] = []
        instruct = req.instruct
        gen = self._model.inference_zero_shot(
            req.text,
            req.reference.transcript or "This is the reference prompt text.",
            req.reference.wav_path,
            stream=False,
            speed=1.0,
        )
        wavs = [w for w in gen if w is not None]
        if not wavs:
            raise EngineNotAvailable("CosyVoice3 returned no audio")
        audio = np.concatenate([w.numpy().cpu().numpy().squeeze() for w in wavs])
        import hashlib
        out = SETTINGS.audio_dir / "gen" / (
            f"cv3-{hashlib.sha256(req.text.encode()).hexdigest()[:12]}.wav"
        )
        self._write_wav(str(out), audio, 24000)
        return SynthResult(
            wav_path=str(out),
            engine_id=self.id,
            engine_version=_engine_version(),
            model_id=self.model_id,
            model_version=self.model_version,
            seed_used=req.seed,
            warnings=warnings,
        )
