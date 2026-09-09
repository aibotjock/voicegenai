"""DSP runner: executes a DspPlan on audio files.

Per-segment pipeline (fixed order, see graph.py):
  graph A (ffmpeg) -> [auto-makeup compressor measured in a pass]
  de-ess (python)
  graph B (ffmpeg: limiter + two-pass loudnorm)
  finalize (python: TP guard, DC removal, padding, 48 kHz/24-bit)

Rehearsal Raw bypasses everything (format-only 48 kHz/24-bit conversion).
"""
from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

from .design import Design
from .graph import DspPlan, build_plan
from .deess import deess as _deess
from .loudness import measure, verify, post_loudnorm_tp_guard


class DspError(RuntimeError):
    pass


@dataclass
class DspReport:
    design_id: str
    builder_version: str
    integrated_lufs: float = float("nan")
    true_peak_db: float = float("nan")
    lra_lu: float = float("nan")
    loudness_ok: bool = False
    tp_guard_gain_db: float = 0.0
    timing_s: dict = field(default_factory=dict)
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "design_id": self.design_id,
            "builder_version": self.builder_version,
            "integrated_lufs": round(self.integrated_lufs, 3),
            "true_peak_db": round(self.true_peak_db, 3),
            "lra_lu": round(self.lra_lu, 3),
            "loudness_ok": self.loudness_ok,
            "tp_guard_gain_db": round(self.tp_guard_gain_db, 3),
            "timing_s": self.timing_s,
            "detail": self.detail,
        }


def _run_ffmpeg(args: list[str], label: str) -> subprocess.CompletedProcess:
    if shutil.which("ffmpeg") is None:
        raise DspError("ffmpeg not found on PATH")
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-y"] + args,
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise DspError(f"ffmpeg {label} failed: {proc.stderr[-2000:]}")
    return proc


def _rms(path: str) -> float:
    y, _ = sf.read(path, dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = y.mean(axis=1)
    return float(np.sqrt(np.mean(np.square(y.astype(np.float64)))))


def _read_mono(path: str) -> tuple[np.ndarray, int]:
    y, sr = sf.read(path, dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = y.mean(axis=1)
    return y, int(sr)


def _write_float(path: str, y: np.ndarray, sr: int) -> None:
    sf.write(path, y, sr, subtype="FLOAT")


def _loudnorm_measure(graph_b: str, path: str) -> dict:
    proc = _run_ffmpeg(
        ["-i", path, "-af", graph_b, "-f", "null", "-"],
        label="loudnorm-measure",
    )
    m = re.search(r"\{[^{}]*\"measured_I\"[^{}]*\}", proc.stderr)
    if not m:
        raise DspError("loudnorm pass-1 produced no measurement JSON")
    return json.loads(m.group(0))


def _loudnorm_linear(graph_b: str, measured: dict) -> str:
    return (
        graph_b
        + f",loudnorm=measured_I={measured['measured_I']}:"
          f"measured_TP={measured['measured_TP']}:"
          f"measured_LRA={measured['measured_LRA']}:"
          f"measured_thresh={measured['measured_thresh']}:"
          f"offset={measured['target_offset']}:linear=true"
    )
```

Wait — this is wrong: the measurement JSON from loudnorm's print_format=json appears at the END of stderr, after the filter has already run with print_format=json. And graph_b already contains the loudnorm filter (measurement mode). To do pass 2 in linear mode, I need a second graph with a loudnorm in linear=true — but you can't just append a second loudnorm after the first in the same graph (the first one already normalized).

Correct approach: graph_b has two variants:
- `graph_b_measure`: alimiter + `loudnorm=I=..:TP=..:LRA=11:print_format=json` → run, parse JSON, output discarded (or kept).
- `graph_b_apply`: alimiter + `loudnorm=I=..:TP=..:LRA=11:measured_I=..:measured_TP=..:measured_LRA=..:measured_thresh=..:offset=..:linear=true:print_format=summary`

So build_plan should emit graph_b without the final loudnorm, and the runner appends the correct loudnorm variant. Let me restructure graph.py: `graph_b` = everything before loudnorm (just the alimiter for now), and the loudnorm params are on the plan (lufs_target, tp_limit_db). The runner constructs the measurement graph and the linear graph.

Let me rewrite the loudnorm section of graph.py accordingly, and continue with the rest of engine.py (which I was in the middle of writing).

<tool_call>
<function=edit_file_tool>
<parameter=edits>
[{"new_content": "def _build_graph_b(d: Design) -> str:\n    \"\"\"Everything before the two-pass loudnorm stage (limiter, etc.).\"\"\"\n    parts = []\n    limit = 10 ** (d.true_peak_limit_db / 20.0)\n    parts.append(f\"alimiter=limit={limit:.5f}:level=false\")\n    return \",\".join(parts)\n\n\ndef loudnorm_measure_graph(d: Design) -> str:\n    return (f\"loudnorm=I={_f(d.lufs_target)}:TP={_f(d.true_peak_limit_db)}:\"\n            f\"LRA=11:print_format=json\")\n\n\ndef loudnorm_apply_graph(d: Design, measured: dict) -> str:\n    return (\n        f\"loudnorm=I={_f(d.lufs_target)}:TP={_f(d.true_peak_limit_db)}:LRA=11:\"\n        f\"measured_I={measured['measured_I']}:measured_TP={measured['measured_TP']}:\"\n        f\"measured_LRA={measured['measured_LRA']}:measured_thresh={measured['measured_thresh']}:\"\n        f\"offset={measured['target_offset']}:linear=true:print_format=summary\"\n    )", "replace_from": "def _build_graph_b(d: Design, lufs: float, tp: float) -> str:\n    parts = []\n    limit = 10 ** (tp / 20.0)\n    parts.append(f\"alimiter=limit={limit:.5f}:level=false\")\n    parts.append(\n        f\"loudnorm=I={_f(lufs)}:TP={_f(tp)}:LRA=11:print_format=json\"\n    )\n    return \",\".join(parts)"}, {"new_content": "    deess = DeessConfig(\n        enabled=d.deess,\n        threshold_db=d.deess_threshold_db,\n        ratio=d.deess_ratio,\n    ) if d.deess else None\n    return DspPlan(\n        design=d,\n        graph_a=_build_graph_a(d),\n        deess=deess,\n        graph_b=_build_graph_b(d),\n        finalize=FinalizeConfig(pad_ms=d.pad_ms),\n        lufs_target=d.lufs_target,\n        tp_limit_db=d.true_peak_limit_db,\n    )", "replace_from": "    deess = DeessConfig(\n        enabled=d.deess,\n        threshold_db=d.deess_threshold_db,\n        ratio=d.deess_ratio,\n    ) if d.deess else None\n    return DspPlan(\n        design=d,\n        graph_a=_build_graph_a(d),\n        deess=deess,\n        graph_b=_build_graph_b(d, d.lufs_target, d.true_peak_limit_db),\n        finalize=FinalizeConfig(pad_ms=d.pad_ms),\n        lufs_target=d.lufs_target,\n        tp_limit_db=d.true_peak_limit_db,\n    )"}]