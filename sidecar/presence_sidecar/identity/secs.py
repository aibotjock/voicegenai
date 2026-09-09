"""Speaker identity: SECS (speaker embedding cosine similarity).

Self-hosted verification model. MVP uses resemblyzer's VoiceEncoder
(d-vector, MIT); the production path targets ECAPA-TDNN / 3D-Speaker class
encoders (see docs/engine-selection.md). The metric is the same contract:
cosine similarity of embeddings against the profile reference.

Gates: SECS >= 0.80 on raw output, >= 0.75 at the most extreme shipped
preset (Boardroom). Verification gate at capture: below threshold ->
profile locked, 3 retries, then re-capture.

Voiceprints are biometric data: keychain-held, never logged, never in
diagnostics exports.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
import soundfile as sf

from ..config import SETTINGS

SECS_GENERATION_MIN = 0.80
SECS_PRESET_MIN = 0.75
SECS_VERIFY_MIN = 0.72
MAX_VERIFY_ATTEMPTS = 3


def _to_16k_mono(wav_path: str) -> tuple[np.ndarray, int]:
    y, sr = sf.read(wav_path, dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = y.mean(axis=1)
    if sr != 16000:
        import torchaudio
        t = torch_from_numpy(y)
        y = torchaudio.functional.resample(t, sr, 16000).numpy()
    return np.asarray(y, dtype=np.float32), 16000


def torch_from_numpy(y: np.ndarray):
    import torch
    return torch.from_numpy(np.ascontiguousarray(y)).unsqueeze(0)


@dataclass
class Embedding:
    vector: np.ndarray
    source_sha256: str


@dataclass
class SimilarityResult:
    secs: float
    gate: str
    ok: bool


class SpeakerSimilarity:
    """Embedding + cosine similarity. Model is lazy-loaded (GPU if present)."""

    def __init__(self) -> None:
        self._enc = None
        self._device = None

    def load(self) -> None:
        if self._enc is not None:
            return
        from resemblyzer import VoiceEncoder
        import torch
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._enc = VoiceEncoder(self._device)

    def embed(self, wav_path: str) -> Embedding:
        if self._enc is None:
            self.load()
        y, sr = _to_16k_mono(wav_path)
        if y.size < 16000 * 0.5:
            raise ValueError("audio too short to embed (<0.5 s)")
        t = torch_from_numpy(y)
        vec = self._enc.embed_utterance(t, verify=False)
        with open(wav_path, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        return Embedding(vector=np.asarray(vec, dtype=np.float32),
                         source_sha256=digest)

    @staticmethod
    def cosine(a: np.ndarray, b: np.ndarray) -> float:
        na = np.linalg.norm(a)
        nb = np.linalg.norm(b)
        if na == 0 or nb == 0:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    def similarity(self, a: Embedding, b: Embedding) -> float:
        return self.cosine(a.vector, b.vector)

    def gate(self, secs: float, kind: str) -> SimilarityResult:
        threshold = {
            "generation": SECS_GENERATION_MIN,
            "preset": SECS_PRESET_MIN,
            "verify": SECS_VERIFY_MIN,
        }.get(kind)
        if threshold is None:
            raise ValueError(f"unknown gate kind {kind!r}")
        return SimilarityResult(secs=secs, gate=kind, ok=secs >= threshold)
