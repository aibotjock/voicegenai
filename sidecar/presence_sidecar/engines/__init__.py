"""Engine registry."""
from __future__ import annotations

from .base import (
    BaseEngine, EngineCapabilities, EngineNotAvailable,
    EngineRef, SynthRequest, SynthResult, GlossarySpan,
)
from .stub import StubEngine
from .chatterbox import ChatterboxEngine
from .cosyvoice3 import CosyVoice3Engine
from .qwen3tts import Qwen3TTSEngine

REGISTRY: dict[str, type[BaseEngine]] = {
    "offline-stub": StubEngine,
    "chatterbox": ChatterboxEngine,
    "cosyvoice3": CosyVoice3Engine,
    "qwen3-tts": Qwen3TTSEngine,
}


def available_engines() -> list[dict]:
    out = []
    for eid, cls in REGISTRY.items():
        try:
            caps = cls().capabilities()
            out.append({"id": eid, "model_id": cls.model_id,
                        "languages": list(caps.languages),
                        "test_only": eid == "offline-stub"})
        except Exception as e:  # pragma: no cover
            out.append({"id": eid, "model_id": cls.model_id,
                        "languages": [], "error": str(e)})
    return out


def get_engine(engine_id: str | None = None, outdir: str | None = None) -> BaseEngine:
    from ..config import SETTINGS
    eid = engine_id or SETTINGS.default_engine
    cls = REGISTRY.get(eid)
    if cls is None:
        raise KeyError(f"unknown engine {eid!r}; known: {sorted(REGISTRY)}")
    if cls is StubEngine and outdir is None:
        outdir = str(SETTINGS.audio_dir / "stub")
    return cls(outdir) if cls is StubEngine else cls()


__all__ = [
    "BaseEngine", "EngineCapabilities", "EngineNotAvailable", "EngineRef",
    "SynthRequest", "SynthResult", "GlossarySpan", "StubEngine",
    "ChatterboxEngine", "CosyVoice3Engine", "Qwen3TTSEngine",
    "REGISTRY", "available_engines", "get_engine",
]
