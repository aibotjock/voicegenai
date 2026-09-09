"""Naturalness: UTMOS (no-reference MOS prediction), 1-5 scale.

Uses utmos-pytorch (fairseq-free PyTorch port, MIT; scores validated to
match the original UTMOS system). Gate: UTMOS >= 4.0 on the eval harness.
"""
from __future__ import annotations

import numpy as np
import soundfile as sf

UTMOS_MIN = 4.0
TARGET_SR = 16000


class Utmos:
    def __init__(self, device: str | None = None) -> None:
        self._model = None
        self.device = device

    def load(self) -> None:
        if self._model is not None:
            return
        from utmos_pytorch import UTMOSScoreTorch
        import torch
        if self.device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model = UTMOSScoreTorch(device=self.device)

    def score(self, wav_path: str) -> float:
        if self._model is None:
            self.load()
        import torch
        import torchaudio
        y, sr = sf.read(wav_path, dtype="float32", always_2d=False)
        if y.ndim > 1:
            y = y.mean(axis=1)
        t = torch.from_numpy(np.ascontiguousarray(y)).unsqueeze(0).to(self.device)
        if sr != TARGET_SR:
            t = torchaudio.functional.resample(t, sr, TARGET_SR)
        with torch.inference_mode():
            s = self._model.score(t)
        return float(s.flatten()[0].item())
