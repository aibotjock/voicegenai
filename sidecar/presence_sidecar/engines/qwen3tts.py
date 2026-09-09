"""Qwen3-TTS adapter (12 Hz, 0.6B/1.7B Base) — verified API.

Model card (Qwen/Qwen3-TTS-12Hz-1.7B-Base, Apache-2.0, 2026):
    from qwen_tts import Qwen3TTSModel
    model = Qwen3TTSModel.from_pretrained("Qwen/Qwen3-TTS-12Hz-1.7B-Base",
                                         device_map="cuda:0", dtype=torch.bfloat16)
    wavs, sr = model.generate_voice_clone(text=..., language="English",
                                         ref_audio=..., ref_text=...)

Voice clone is the Base model; CustomVoice has fixed premium timbres with
optional `instruct` (Layer B candidate), VoiceDesign does natural-language
voice design. For CPU-only paths the 0.6B Base is the practical choice.
"""
from __future__ import annotations

import hashlib
import os

import numpy as np

from ..config import SETTINGS
from .base import (
    BaseEngine, EngineCapabilities, EngineNotAvailable, SynthRequest, SynthResult,
)

MODEL_ID = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
MODEL_VERSION = "0.6B-12Hz"


class Qwen3TTSEngine(BaseEngine):
    id = "qwen3-tts"
    model_id = MODEL_ID
    model_version = MODEL_VERSION

    def __init__(self, model_id: str | None = None) -> None:
        self._model = None
        self._loaded = False
        self._device = "cpu"
        if model_id:
            self.model_id = model_id
            self.model_version = model_id.split("/")[-1].replace(
                "Qwen3-TTS-", "")

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            supports_reference=True,
            supports_phoneme_inpainting=False,
            supports_seed=True,
            instruction_control=True,   # Layer B: `instruct` param (P2)
            streaming=True,
            languages=("en", "zh", "ja", "ko", "de", "fr", "ru", "pt", "es", "it"),
            output_rate=24000,
        )

    def load(self) -> None:
        if self._loaded:
            return
        try:
            from qwen_tts import Qwen3TTSModel  # type: ignore
        except ImportError as e:
            raise EngineNotAvailable(
                "qwen-tts is not installed. pip install -U qwen-tts "
                "(official Qwen3-TTS package; weights Apache-2.0 — re-verify "
                "on bump)."
            ) from e
        import torch
        self._device = self._pick_device()
        dtype = torch.bfloat16 if self._device == "cuda" else torch.float32
        kwargs = {}
        if os.environ.get("QWEN_TTS_FLASH_ATTN") == "1":
            kwargs["attn_implementation"] = "flash_attention_2"
        local = str(SETTINGS.models_dir / "qwen3-tts" / self.model_id.split("/")[-1])
        if os.path.isdir(local) and os.listdir(local):
            src = local
        else:
            src = self.model_id
        self._model = Qwen3TTSModel.from_pretrained(
            src, device_map=self._device, dtype=dtype, **kwargs
        )
        self._loaded = True

    def synthesize(self, req: SynthRequest) -> SynthResult:
        if not self._loaded:
            self.load()
        if req.reference is None:
            raise EngineNotAvailable("Qwen3-TTS requires a speaker reference")
        import torch
        if req.seed is not None:
            torch.manual_seed(req.seed)
        warnings: list[str] = []
        kwargs: dict = {}
        if req.instruct:
            # Layer B instruction string: visible in UI, recorded in provenance
            kwargs["instruct"] = req.instruct
        with torch.inference_mode():
            wavs, sr = self._model.generate_voice_clone(
                text=req.text,
                language="English",
                ref_audio=req.reference.wav_path,
                ref_text=req.reference.transcript or " ",
                **kwargs,
            )
        wav = np.asarray(wavs[0], dtype=np.float32)
        out = SETTINGS.audio_dir / "gen" / (
            f"qw3-{hashlib.sha256(req.text.encode()).hexdigest()[:12]}.wav"
        )
        self._write_wav(str(out), wav, int(sr))
        return SynthResult(
            wav_path=str(out),
            engine_id=self.id,
            engine_version=f"qwen-tts {self.model_version}",
            model_id=self.model_id,
            model_version=self.model_version,
            seed_used=req.seed,
            warnings=warnings,
        )
