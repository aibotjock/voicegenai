"""DSP runner: executes a DspPlan on audio files.

Per-segment pipeline (fixed order, see graph.py):
  graph A (ffmpeg: resample, rubberband, EQ, compressor with auto makeup)
  de-ess (python, 6-9 kHz band split)
  graph B (ffmpeg: limiter, then two-pass loudnorm)
  finalize (python: TP guard, DC removal, padding, 48 kHz/24-bit)

Rehearsal Raw bypasses everything (format-only 48 kHz/24-bit conversion).

Compressor auto makeup: pass 1 runs the compressor with makeup=0; the
measured RMS reduction becomes the makeup gain for the production run
(clamped 0..9 dB). Deterministic for identical input.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

from .design import Design
from .graph import (
    DspPlan, build_plan, loudnorm_apply_graph, loudnorm_measure_graph,
)
from .deess import deess as _deess_fn
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


def _parse_loudnorm_json(stderr: str) -> dict:
    """Parse loudnorm pass-1 JSON (keys: input_i, input_tp, input_lra,
    input_thresh, target_offset ...)."""
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", stderr)
    if not m:
        raise DspError("loudnorm pass-1 produced no measurement JSON")
    return json.loads(m.group(0))


def _finalize(in_path: str, out_path: str, plan: DspPlan,
              timings: dict[str, float]) -> float:
    """Post-loudnorm TP guard, DC removal, padding, 24-bit master."""
    t0 = time.time()
    y, sr = _read_mono(in_path)
    cfg = plan.finalize
    tp_gain = 0.0
    if cfg.tp_guard:
        # measure on the signal before padding (padding adds only silence)
        import soundfile as sfmod
        tmp = str(Path(in_path).with_suffix(".tpg.wav"))
        sfmod.write(tmp, y, sr, subtype="FLOAT")
        tp_gain = post_loudnorm_tp_guard(tmp, plan.tp_limit_db)
        if tp_gain:
            y, _ = _read_mono(tmp)
            Path(tmp).unlink(missing_ok=True)
    if cfg.dc_remove:
        n = max(1, int(0.1 * sr))
        dc = float(y[:n].mean() + y[-n:].mean()) / 2.0
        y = y - dc
    if cfg.pad_ms:
        pad = int(cfg.pad_ms / 1000.0 * sr)
        y = np.concatenate(
            [np.zeros(pad, np.float32), y, np.zeros(pad, np.float32)]
        )
    sf.write(out_path, y, sr, subtype=f"PCM_{cfg.bits}")
    timings["finalize"] = round(time.time() - t0, 3)
    return tp_gain


def run_dsp(input_path: str, output_path: str, design: Design,
            workdir: str | Path) -> DspReport:
    """Process one audio file through the full plan."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    plan = build_plan(design)
    timings: dict[str, float] = {}
    report = DspReport(design_id=design.id, builder_version=plan.builder_version)

    if plan.bypass:
        t0 = time.time()
        y, sr = _read_mono(input_path)
        sf.write(output_path, y, 48000, subtype="PCM_24")
        timings["convert"] = round(time.time() - t0, 3)
        m = measure(output_path)
        report.integrated_lufs = m["integrated_lufs"]
        report.true_peak_db = m["true_peak_db"]
        report.lra_lu = m["lra_lu"]
        report.detail = "rehearsal-raw: no processing (original loudness)"
        report.timing_s = timings
        return report

    # --- graph A: optional compressor auto-makeup pass -------------------
    t0 = time.time()
    has_comp = design.comp_ratio >= 2.0
    if has_comp and "makeup=1dB" in plan.graph_a:
        g1 = plan.graph_a.replace("makeup=1dB", "makeup=0dB")
        _run_ffmpeg(["-i", input_path, "-af", g1, str(workdir / "a1.wav")],
                    "graphA-pass1")
        rms_in = _rms(input_path)
        rms_out = _rms(str(workdir / "a1.wav"))
        makeup = 0.0
        if rms_out > 1e-6 and rms_in > rms_out:
            makeup = min(9.0, max(0.0, 20 * np.log10(rms_in / rms_out)))
        g2 = plan.graph_a.replace("makeup=1dB", f"makeup={makeup:.2f}dB")
    else:
        g2 = plan.graph_a
    _run_ffmpeg(["-i", input_path, "-af", g2, str(workdir / "a2.wav")],
                "graphA")
    timings["graph_a"] = round(time.time() - t0, 3)

    # --- de-ess (python) ---------------------------------------------------
    if plan.deess and plan.deess.enabled:
        t0 = time.time()
        y, sr = _read_mono(str(workdir / "a2.wav"))
        out = _deess_fn(
            y, sr=sr,
            threshold_db=plan.deess.threshold_db, ratio=plan.deess.ratio,
            attack_ms=plan.deess.attack_ms, release_ms=plan.deess.release_ms,
            knee_db=plan.deess.knee_db,
        )
        _write_float(str(workdir / "a3.wav"), out, sr)
        timings["deess"] = round(time.time() - t0, 3)
        cur = "a3.wav"
    else:
        cur = "a2.wav"

    # --- graph B: limiter + two-pass loudnorm ------------------------------
    t0 = time.time()
    proc = _run_ffmpeg(["-i", str(workdir / cur),
                        "-af", plan.graph_b + "," + loudnorm_measure_graph(design),
                        "-f", "null", "-"], "graphB-measure")
    measured = _parse_loudnorm_json(proc.stderr)
    apply_graph = plan.graph_b + "," + loudnorm_apply_graph(design, measured)
    _run_ffmpeg(["-i", str(workdir / cur), "-af", apply_graph,
                 str(workdir / "a4.wav")], "graphB-apply")
    timings["graph_b"] = round(time.time() - t0, 3)

    # --- finalize ------------------------------------------------------------
    tp_gain = _finalize(str(workdir / "a4.wav"), output_path, plan, timings)
    report.tp_guard_gain_db = tp_gain

    m = measure(output_path)
    report.integrated_lufs = m["integrated_lufs"]
    report.true_peak_db = m["true_peak_db"]
    report.lra_lu = m["lra_lu"]
    rep = verify(output_path, design.lufs_target, design.true_peak_limit_db)
    report.loudness_ok = rep.ok
    report.detail = rep.detail
    report.timing_s = timings
    return report


# ---------------------------------------------------------------------------
# Segment joiner: crossfades + pause shaping
# ---------------------------------------------------------------------------

@dataclass
class JoinItem:
    path: str
    # boundary BEFORE this item: None (first), "join", or "pause:<ms>"
    boundary: str | None = None


CROSSFADE_S = 0.024  # <= 30 ms per spec


def join_segments(items: list[JoinItem], output_path: str,
                  rate: int = 48000, design: Design | None = None) -> DspReport:
    """Join processed segments.

    Intra-paragraph boundary: 24 ms crossfade (prosody continuity).
    Paragraph boundary: crossfade into shaped silence (pause_shaping_ms,
    minimum 250 ms) then concat — gravity at section edges.
    """
    if not items:
        raise DspError("no segments to join")
    if len(items) == 1:
        shutil.copyfile(items[0].path, output_path)
        m = measure(output_path)
        return DspReport(
            design_id=(design.id if design else "n/a"),
            builder_version="join-1.0",
            integrated_lufs=m["integrated_lufs"],
            true_peak_db=m["true_peak_db"],
            lra_lu=m["lra_lu"],
            loudness_ok=True,
        )

    cmd: list[str] = []
    for it in items:
        cmd += ["-i", it.path]
    n_pauses = 0
    for it in items:
        if isinstance(it.boundary, str) and it.boundary.startswith("pause:"):
            cmd += ["-f", "lavfi", "-i", f"anullsrc=r={rate}:cl=mono"]
            n_pauses += 1

    fg: list[str] = []
    for i, it in enumerate(items):
        fade = "0" if i == 0 else "0.005"
        fg.append(
            f"[{i}:a]aresample={rate},aformat=sample_fmts=fltp:"
            f"channel_layouts=mono,afade=t=in:d={fade}[s{i}]"
        )
    cur = "s0"
    sil_counter = 0
    for idx, it in enumerate(items[1:], start=1):
        b = it.boundary
        if b == "join" or b is None:
            nxt = f"j{idx}"
            fg.append(f"[{cur}][s{idx}]acrossfade=d={CROSSFADE_S}:c1=tri:c2=tri[{nxt}]")
            cur = nxt
        elif isinstance(b, str) and b.startswith("pause:"):
            ms = int(b.split(":")[1])
            pause_s = max(ms, 250) / 1000.0
            sil_in = len(items) + sil_counter
            sil_counter += 1
            st = f"sil{idx}"
            fg.append(
                f"[{sil_in}:a]atrim=0:{pause_s:.4f},asetpts=PTS-STARTPTS[{st}]"
            )
            mid = f"m{idx}"
            fg.append(f"[{cur}][{st}]acrossfade=d={CROSSFADE_S}:c1=tri:c2=tri[{mid}]")
            nxt = f"j{idx}"
            fg.append(f"[{mid}][s{idx}]concat=n=2:v=0:a=1[{nxt}]")
            cur = nxt
    filtergraph = ";".join(fg)
    _run_ffmpeg(
        cmd + ["-filter_complex", filtergraph, "-map", f"[{cur}]",
               "-ar", str(rate), output_path],
        "join",
    )
    m = measure(output_path)
    return DspReport(
        design_id=(design.id if design else "n/a"),
        builder_version="join-1.0",
        integrated_lufs=m["integrated_lufs"],
        true_peak_db=m["true_peak_db"],
        lra_lu=m["lra_lu"],
        loudness_ok=True,
    )
