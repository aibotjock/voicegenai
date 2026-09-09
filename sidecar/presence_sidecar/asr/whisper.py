"""Local ASR (faster-whisper class) for the per-segment WER self-check.

Model: large-v3-turbo (CTranslate2) — the canonical CT2 turbo conversion is
the deepdml mirror (Systran hosts v1-v3 but no turbo build); small.en
fallback for CPU. Runs fully offline after the model is cached in the model
registry. Respects PRESENCE_DEVICE (CPU-only path stays functional).
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

from ..config import SETTINGS

# model_size -> HF repo (pinned; re-verify license on bump)
_REPOS = {
    "large-v3-turbo": "deepdml/faster-whisper-large-v3-turbo-ct2",
    "small.en": "Systran/faster-whisper-small.en",
    "large-v3": "Systran/faster-whisper-large-v3",
}


@dataclass
class Transcription:
    text: str
    language: str
    duration_s: float


class WhisperASR:
    def __init__(self, model_size: str | None = None, device: str | None = None) -> None:
        self.model_size = model_size
        self.device = device
        self._model = None

    def load(self) -> None:
        if self._model is not None:
            return
        from faster_whisper import WhisperModel
        if self.device is None:
            forced = os.environ.get("PRESENCE_DEVICE", "").strip().lower()
            if forced in ("cpu", "cuda"):
                self.device = forced
            else:
                import torch
                self.device = "cuda" if torch.cuda.is_available() else "cpu"
        if self.model_size is None:
            self.model_size = "large-v3-turbo" if self.device == "cuda" else "small.en"
        from huggingface_hub import snapshot_download
        cache = str(SETTINGS.models_dir / "whisper" / self.model_size)
        local = snapshot_download(_REPOS[self.model_size], local_dir=cache)
        self._model = WhisperModel(local, device=self.device,
                                   compute_type="float16" if self.device == "cuda" else "int8")

    def transcribe(self, wav_path: str) -> Transcription:
        if self._model is None:
            self.load()
        segments, info = self._model.transcribe(
            wav_path, language="en", beam_size=1, vad_filter=True,
        )
        text = " ".join(s.text.strip() for s in segments).strip()
        return Transcription(text=text, language=info.language,
                             duration_s=info.duration)
