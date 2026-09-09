"""Objective quality harness (spec §7) — CI-able, replaces ad-hoc listening.

Metrics on the fixed 50-sentence eval script + reference capture:
  WER      local ASR round-trip (faster-whisper)          gate <= 3%
  SECS     speaker embedding cosine (resemblyzer)        gate >= 0.80 raw,
                                                         >= 0.75 @ Boardroom
  UTMOS    no-reference naturalness (1-5)                gate >= 4.0
  loudness integrated LUFS / true peak / LRA             gate ±0.5 LU, -1.5 dBTP
  joins    spectral-flux click scan at segment joins     gate: zero artifacts
  RTF      realtime factor on target hardware            budget: >=5x GPU

A run writes a scorecard (JSON + markdown) to docs/quality/<date>/.
A model or DSP change that fails gates does not ship.
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import hashlib
import json
import platform
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

from . import APP_VERSION
from .asr.whisper import WhisperASR
from .asr.wer import compute_wer
from .dsp import PRESETS, run_dsp, join_segments, JoinItem, measure
from .identity.secs import SpeakerSimilarity, SECS_GENERATION_MIN, SECS_PRESET_MIN
from .naturalness.utmos import Utmos, UTMOS_MIN

GATE_WER = 0.03
GATE_LUFS_TOL = 0.5
GATE_TP_TOL = 0.2
EVAL_SCRIPT = Path(__file__).resolve().parents[2] / "eval" / "eval_script_50.json"


@dataclass
class SegmentResult:
    index: int
    raw_text: str
    spoken_text: str
    hypothesis: str
    wer: float
    secs: float
    utmos: float
    audio_s: float
    synth_s: float
    flagged: bool
    wav_path: str = ""
    retries: int = 0


@dataclass
class HarnessReport:
    engine_id: str
    engine_version: str
    model_id: str
    model_version: str
    reference_sha256: str
    design_id: str
    results: list[SegmentResult] = field(default_factory=list)
    # aggregates
    wer_mean: float = float("nan")
    secs_mean: float = float("nan")
    utmos_mean: float = float("nan")
    rtf: float = float("nan")
    flagged_segments: int = 0
    # master (joined + DSP)
    master_lufs: float = float("nan")
    master_tp_db: float = float("nan")
    master_lra: float = float("nan")
    join_artifacts: int = -1
    # identity at presets
    preset_secs: dict = field(default_factory=dict)
    # gates
    gates: dict = field(default_factory=dict)
    all_gates_pass: bool = False
    generated_at: str = ""
    device: str = ""
    host: str = ""

    def to_dict(self) -> dict:
        return {
            "engine": {"id": self.engine_id, "version": self.engine_version,
                       "model_id": self.model_id, "model_version": self.model_version},
            "reference_sha256": self.reference_sha256,
            "design": self.design_id,
            "generated_at": self.generated_at,
            "environment": {"device": self.device, "host": platform.node(),
                            "python": platform.python_version(),
                            "system": platform.platform()},
            "aggregate": {
                "wer_mean": round(self.wer_mean, 5),
                "secs_mean": round(self.secs_mean, 4),
                "utmos_mean": round(self.utmos_mean, 3),
                "rtf": round(self.rtf, 3),
                "flagged_segments": self.flagged_segments,
                "master_lufs": round(self.master_lufs, 2),
                "master_tp_db": round(self.master_tp_db, 2),
                "master_lra": round(self.master_lra, 2),
                "join_artifacts": self.join_artifacts,
                "preset_secs": {k: round(v, 4) for k, v in self.preset_secs.items()},
            },
            "segments": [dataclasses.asdict(r) for r in self.results],
            "gates": self.gates,
            "all_gates_pass": self.all_gates_pass,
        }


def spectral_flux_click_scan(
    y: np.ndarray, sr: int, boundaries: list[int], guard_ms: float = 2.0
) -> int:
    """Count clicks at join boundaries (spectral-difference detector).

    For each boundary: energy of the first difference of the signal in a
    ±guard window compared to the local median. A click/step produces a
    broadband transient far above the local baseline. Validated against
    injected impulses in tests (tests/test_dsp_golden.py).
    """
    if not boundaries:
        return 0
    n = int(sr * guard_ms / 1000.0)
    d = np.abs(np.diff(y, prepend=y[0]))
    window = np.ones(n) / n
    art = 0
    for b in boundaries:
        lo = max(0, b - n)
        hi = min(len(d), b + n)
        local = d[max(0, b - int(sr * 0.05)):b + int(sr * 0.05)]
        if local.size == 0:
            continue
        med = np.median(local)
        peak = float(np.max(d[lo:hi])) if hi > lo else 0.0
        # a click is >12x the local transient baseline
        if med > 1e-8 and peak > med * 12.0 + 1e-5:
            art += 1
        elif med <= 1e-8 and peak > 1e-3:
            art += 1
    return art


class Harness:
    def __init__(self, engine=None, device: str | None = None) -> None:
        self.engine = engine
        self.asr = WhisperASR()
        self.secs = SpeakerSimilarity()
        self.utmos = Utmos()
        self.device = device

    def load(self, reference_path: str) -> dict:
        """Load models + reference embedding. Returns context."""
        self.asr.load()
        self.utmos.load()
        self.secs.load()
        ref = self.secs.embed(reference_path)
        y, sr = sf.read(reference_path, dtype="float32", always_2d=False)
        with open(reference_path, "rb") as f:
            ref_sha = hashlib.sha256(f.read()).hexdigest()
        return {"ref_embed": ref, "ref_sha": ref_sha, "ref_dur_s": len(y) / sr}

    def run(
        self,
        reference_path: str,
        reference_transcript: str,
        design=None,
        limit: int | None = None,
        workdir: str | Path = "/tmp/presence-harness",
        seed: int = 1234,
    ) -> HarnessReport:
        from .engines.base import EngineRef, SynthRequest

        design = design or PRESETS["podcast"]
        workdir = Path(workdir)
        (workdir / "segs").mkdir(parents=True, exist_ok=True)
        ctx = self.load(reference_path)
        sentences = load_eval_sentences()[: limit or 50]
        caps = self.engine.capabilities()

        rep = HarnessReport(
            engine_id=self.engine.id,
            engine_version=getattr(self.engine, "engine_version", ""),
            model_id=self.engine.model_id,
            model_version=self.engine.model_version,
            reference_sha256=ctx["ref_sha"],
            design_id=design.id,
            generated_at=_dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            device=self.device or "auto",
        )
        ref_obj = EngineRef(wav_path=reference_path, transcript=reference_transcript)
        total_audio = 0.0
        total_synth = 0.0
        from .text_pipeline.normalize import normalize as _normalize
        for i, raw_text in enumerate(sentences):
            # The harness runs the product's core loop: raw script -> spoken
            # form -> engine. WER ground truth is the SPOKEN form (what a
            # perfect engine would say), not the raw script text.
            text = _normalize(raw_text).text
            t0 = time.time()
            res = self.engine.synthesize(SynthRequest(
                text=text, reference=ref_obj, seed=seed + i,
            ))
            synth_s = time.time() - t0
            wav = res.wav_path
            audio = sf.info(wav)
            audio_s = audio.duration
            total_audio += audio_s
            total_synth += synth_s
            hyp = self.asr.transcribe(wav).text
            wer = compute_wer(hyp, text)
            seg_secs = self.secs.similarity(ctx["ref_embed"], self.secs.embed(wav))
            utmos_score = self.utmos.score(wav)
            seg = SegmentResult(
                index=i, raw_text=raw_text, spoken_text=text, hypothesis=hyp,
                wer=wer, secs=seg_secs, utmos=utmos_score, audio_s=audio_s,
                synth_s=synth_s, flagged=wer > 0.08, wav_path=wav,
            )
            rep.results.append(seg)

        wers = [r.wer for r in rep.results]
        rep.wer_mean = statistics.mean(wers) if wers else float("nan")
        rep.secs_mean = statistics.mean([r.secs for r in rep.results])
        rep.utmos_mean = statistics.mean([r.utmos for r in rep.results])
        rep.flagged_segments = sum(1 for r in rep.results if r.flagged)
        rep.rtf = (total_audio / total_synth) if total_synth > 0 else float("nan")

        # master: join all segments -> full DSP chain (design)
        seg_paths = []
        for r in rep.results:
            info = sf.info(r.wav_path)
            y, sr_in = sf.read(r.wav_path, dtype="float32", always_2d=False)
            if y.ndim > 1:
                y = y.mean(axis=1)
            p = workdir / "segs" / f"seg{r.index:03d}.wav"
            sf.write(str(p), y, sr_in, subtype="FLOAT")
            seg_paths.append(p)
        items = [
            JoinItem(str(p), None if i == 0 else "join")
            for i, p in enumerate(seg_paths)
        ]
        joined = workdir / "joined.wav"
        if len(items) > 1:
            join_segments(items, str(joined))
        else:
            joined = Path(seg_paths[0])
        master = workdir / "master.wav"
        dsp_rep = run_dsp(str(joined), str(master), design, workdir / "dspwk")
        m = measure(str(master))
        rep.master_lufs = m["integrated_lufs"]
        rep.master_tp_db = m["true_peak_db"]
        rep.master_lra = m["lra_lu"]
        # join-click scan on the joined (pre-DSP) master
        y, sr = sf.read(str(joined), dtype="float32", always_2d=False)
        if y.ndim > 1:
            y = y.mean(axis=1)
        boundaries = _boundary_indices(seg_paths, sr)
        rep.join_artifacts = spectral_flux_click_scan(y, sr, boundaries)

        # identity at presets (raw + every shipped preset)
        rep.preset_secs = {"raw": rep.secs_mean}
        for pid in ("boardroom", "keynote", "calm-expert", "podcast"):
            out = workdir / f"preset-{pid}.wav"
            run_dsp(str(joined), str(out), PRESETS[pid], workdir / f"dspwk-{pid}")
            s = self.secs.similarity(ctx["ref_embed"], self.secs.embed(str(out)))
            rep.preset_secs[pid] = s

        # gates
        rep.gates = {
            "wer_le_3pct": rep.wer_mean <= GATE_WER,
            "secs_ge_080_raw": rep.preset_secs["raw"] >= SECS_GENERATION_MIN,
            "secs_ge_075_boardroom": rep.preset_secs.get("boardroom", 0) >= SECS_PRESET_MIN,
            "utmos_ge_4": rep.utmos_mean >= UTMOS_MIN,
            "lufs_within_0.5": abs(rep.master_lufs - design.lufs_target) <= GATE_LUFS_TOL,
            "tp_le_-1.5": rep.master_tp_db <= design.true_peak_limit_db + GATE_TP_TOL,
            "zero_join_clicks": rep.join_artifacts == 0,
        }
        rep.all_gates_pass = all(rep.gates.values())
        return rep


def load_eval_sentences() -> list[str]:
    data = json.loads(Path(EVAL_SCRIPT).read_text(encoding="utf-8"))
    return data["sentences"]


def _boundary_indices(seg_paths: list[Path], sr: int) -> list[int]:
    """Approximate sample offsets of joins in the joined file."""
    idx = []
    pos = 0
    crossfade = int(0.024 * sr)
    for i, p in enumerate(seg_paths):
        info = sf.info(str(p))
        if i == 0:
            pos = int(info.frames)
            continue
        idx.append(pos)
        pos += int(info.frames) - crossfade
    return idx


def scorecard_markdown(rep: HarnessReport) -> str:
    g = rep.gates
    lines = [
        "# Presence Studio quality scorecard",
        "",
        f"- generated: {rep.generated_at}",
        f"- engine: `{rep.engine_id}` {rep.engine_version} "
        f"({rep.model_id} {rep.model_version})",
        f"- reference sha256: `{rep.reference_sha256[:16]}…`",
        f"- design: `{rep.design_id}`",
        "",
        "## Gates",
        "",
        "| gate | target | measured | pass |",
        "|---|---|---|---|",
        f"| WER | ≤ 0.03 | {rep.wer_mean:.4f} | {'✅' if g['wer_le_3pct'] else '❌'} |",
        f"| SECS raw | ≥ 0.80 | {rep.preset_secs.get('raw', float('nan')):.3f} | {'✅' if g['secs_ge_080_raw'] else '❌'} |",
        f"| SECS @Boardroom | ≥ 0.75 | {rep.preset_secs.get('boardroom', float('nan')):.3f} | {'✅' if g['secs_ge_075_boardroom'] else '❌'} |",
        f"| UTMOS | ≥ 4.0 | {rep.utmos_mean:.2f} | {'✅' if g['utmos_ge_4'] else '❌'} |",
        f"| Integrated loudness | ±0.5 LU | {rep.master_lufs:.2f} LUFS | {'✅' if g['lufs_within_0.5'] else '❌'} |",
        f"| True peak | ≤ -1.5 dBTP | {rep.master_tp_db:.2f} dBTP | {'✅' if g['tp_le_-1.5'] else '❌'} |",
        f"| Join clicks | 0 | {rep.join_artifacts} | {'✅' if g['zero_join_clicks'] else '❌'} |",
        "",
        "## Detail",
        "",
        f"- RTF (GPU synth): {rep.rtf:.2f}× realtime",
        f"- flagged segments (WER>8%): {rep.flagged_segments}",
        f"- LRA: {rep.master_lra:.2f} LU",
        f"- identity at presets: "
        + ", ".join(f"{k}={v:.3f}" for k, v in rep.preset_secs.items()),
        "",
        f"**Overall: {'ALL GATES PASS' if rep.all_gates_pass else 'GATES FAILED — does not ship'}**",
    ]
    return "\n".join(lines) + "\n"


def write_artifacts(rep: HarnessReport, outdir: str | Path) -> Path:
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "scorecard.json").write_text(
        json.dumps(rep.to_dict(), indent=2), encoding="utf-8")
    (outdir / "scorecard.md").write_text(
        scorecard_markdown(rep), encoding="utf-8")
    return outdir


def main() -> int:  # `presence-harness` entry point
    import argparse

    from .engines import get_engine
    from .config import SETTINGS

    ap = argparse.ArgumentParser(prog="presence-harness")
    ap.add_argument("--engine", default=SETTINGS.default_engine)
    ap.add_argument("--reference", required=True)
    ap.add_argument("--transcript", default="")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--seed", type=int, default=1234)
    args = ap.parse_args()

    engine = get_engine(args.engine)
    engine.load()
    harness = Harness(engine=engine)
    rep = harness.run(args.reference, args.transcript, limit=args.limit,
                      seed=args.seed)
    out = Path(args.out) if args.out else Path("docs/quality") / _dt.date.today().isoformat() / engine.id
    write_artifacts(rep, out)
    print(scorecard_markdown(rep))
    print(f"artifacts: {out}")
    return 0 if rep.all_gates_pass else 1
