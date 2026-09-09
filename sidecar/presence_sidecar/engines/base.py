"""Engine contracts.

An engine is a swappable component: text + speaker reference -> audio.
All engines flow through the same local pipeline (text pipeline, WER
self-check, DSP chain, provenance) — the engine is never a separate product.
"""
from __future__ import annotations

import abc
import dataclasses
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EngineCapabilities:
    supports_reference: bool = True
    supports_phoneme_inpainting: bool = False
    supports_seed: bool = False
    instruction_control: bool = False      # Layer B (P2)
    streaming: bool = False
    languages: tuple[str, ...] = ("en",)
    output_rate: int = 24000


@dataclass
class EngineRef:
    """Speaker reference: a verified window of the user's own voice."""
    wav_path: str
    transcript: str = ""


@dataclass
class GlossarySpan:
    """Engine-level phoneme inpainting request (from the glossary)."""
    start: int
    end: int
    term: str
    phonemes: str | None = None


@dataclass
class SynthRequest:
    text: str
    reference: EngineRef | None = None
    seed: int | None = None
    glossary_spans: list[GlossarySpan] = field(default_factory=list)
    instruct: str | None = None          # Layer B (P2), off by default


@dataclass
class SynthResult:
    wav_path: str
    engine_id: str
    engine_version: str
    model_id: str
    model_version: str
    seed_used: int | None
    warnings: list[str] = field(default_factory=list)


class EngineNotAvailable(RuntimeError):
    """Engine deps/weights missing or license-gated."""


class BaseEngine(abc.ABC):
    id: str = "base"
    model_id: str = ""
    model_version: str = ""

    @abc.abstractmethod
    def capabilities(self) -> EngineCapabilities: ...

    @abc.abstractmethod
    def load(self) -> None:
        """Load model weights (from the model registry cache)."""

    @abc.abstractmethod
    def synthesize(self, req: SynthRequest) -> SynthResult: ...

    def health(self) -> dict:
        return {
            "engine": self.id,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "loaded": getattr(self, "_loaded", False),
            "capabilities": dataclasses.asdict(self.capabilities()),
        }

    # -- helpers ---------------------------------------------------------

    def _write_wav(self, path: str, wav, sr: int) -> None:
        import numpy as np
        import soundfile as sf
        if hasattr(wav, "numpy"):
            wav = wav.numpy()
        wav = np.asarray(wav, dtype=np.float32)
        if wav.ndim > 1:
            wav = wav.mean(axis=0)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        sf.write(path, wav, sr, subtype="FLOAT")

    @staticmethod
    def _pick_device() -> str:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        try:
            if torch.backends.mps.is_available():
                return "mps"
        except Exception:
            pass
        return "cpu"
