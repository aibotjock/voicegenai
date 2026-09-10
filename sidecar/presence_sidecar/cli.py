"""Presence Studio CLI.

`presence` — end-to-end text-to-speech with the full local pipeline:
  text pipeline -> engine -> per-segment WER self-check -> DSP design
  -> export with provenance + loudness report.

Examples:
  presence presets
  presence generate "Hello from Presence Studio." --out out.wav
  presence generate script.md --engine chatterbox --design keynote
  presence sidecar            # start the local API (127.0.0.1, token auth)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import APP_NAME, APP_VERSION
from .config import SETTINGS


def _cmd_presets(args) -> int:
    from .dsp import PRESETS, BROADCAST_LUFS, DIGITAL_LUFS
    print(f"{'preset':16} {'character':44} params-hash")
    for p in PRESETS.values():
        print(f"{p.id:16} {p.character[:44]:44} {p.params_hash()}")
    print(f"\nloudness targets: digital {DIGITAL_LUFS} LUFS, broadcast {BROADCAST_LUFS} LUFS")
    return 0


def _cmd_generate(args) -> int:
    import time
    import numpy as np
    import soundfile as sf

    from .text_pipeline import prepare_script
    from .text_pipeline.glossary import Pronunciation
    from .engines import get_engine
    from .engines.base import EngineRef, SynthRequest
    from .asr.whisper import WhisperASR
    from .asr.wer import compute_wer, WER_THRESHOLD
    from .dsp import get_preset, run_dsp, join_segments, JoinItem, measure
    from .export.provenance import Provenance
    from .export.writer import export

    src = Path(args.script)
    if src.exists():
        raw = src.read_text(encoding="utf-8")
        fmt = src.suffix.lstrip(".").lower()
    else:
        raw, fmt = args.script, "text"

    design = get_preset(args.design, None if args.lufs is None else args.lufs)
    engine = get_engine(args.engine)
    engine.load()

    prepared = prepare_script(
        raw, fmt=fmt if fmt in ("md", "markdown", "txt", "text") else "text",
        engine_supports_phonemes=engine.capabilities().supports_phoneme_inpainting,
    )
    if not prepared.segments:
        print("error: script produced no segments", file=sys.stderr)
        return 2
    print(f"script: {len(prepared.segments)} segments, "
          f"{len(prepared.applied_rules)} normalization rules applied")
    if prepared.warnings:
        for w in prepared.warnings:
            print(f"warning: {w}")

    reference = None
    if args.reference:
        reference = EngineRef(wav_path=args.reference, transcript=args.transcript or "")
    elif engine.capabilities().supports_reference:
        print(f"error: engine {engine.id} requires --reference (a clean "
              "capture of your own voice)", file=sys.stderr)
        return 2

    asr = WhisperASR() if not args.no_check else None
    if asr is not None and not args.no_check:
        asr.load()

    outdir = Path(args.out).parent if Path(args.out).suffix else Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    workdir = outdir / ".work"
    (workdir / "segs").mkdir(parents=True, exist_ok=True)

    seg_files = []
    flagged = 0
    t_start = time.time()
    for seg in prepared.segments:
        res = engine.synthesize(SynthRequest(
            text=seg.text, reference=reference, seed=args.seed,
        ))
        # normalize segment container to 48k float
        y, sr_in = sf.read(res.wav_path, dtype="float32", always_2d=False)
        if y.ndim > 1:
            y = y.mean(axis=1)
        p = workdir / "segs" / f"seg{seg.index:03d}.wav"
        sf.write(str(p), y, sr_in, subtype="FLOAT")
        seg_files.append((p, seg))
        if asr is not None:
            hyp = asr.transcribe(str(p)).text
            wer = compute_wer(hyp, seg.text)
            if wer > WER_THRESHOLD:
                flagged += 1
                print(f"  [flag] segment {seg.index}: WER {wer:.1%} — "
                      f"said: {hyp!r}")
    joined = workdir / "joined.wav"
    if len(seg_files) > 1:
        join_segments(
            [JoinItem(str(p), None if i == 0 else (
                f"pause:{max(design.pause_shaping_ms, 0)}" if s.is_paragraph_start and design.pause_shaping_ms else "join"))
             for i, (p, s) in enumerate(seg_files)],
            str(joined), design=design)
    else:
        joined = Path(seg_files[0][0])

    master = workdir / "master.wav"
    dsp_rep = run_dsp(str(joined), str(master), design, workdir / "dsp")
    m = measure(str(master))
    elapsed = time.time() - t_start
    print(f"dsp: LUFS {m['integrated_lufs']:.2f} / TP {m['true_peak_db']:.2f} dBTP "
          f"(design={design.id}) | flagged segments: {flagged}")

    prov = Provenance(
        engine_id=res.engine_id, engine_version=res.engine_version,
        model_id=res.model_id, model_version=res.model_version,
        design_id=design.id, design_name=design.name,
        design_params_hash=design.params_hash(), seed=args.seed,
        script_sha256=prepared.text_sha256,
        loudness={"integrated_lufs": m["integrated_lufs"],
                  "true_peak_db": m["true_peak_db"], "lra_lu": m["lra_lu"]},
    )
    stem = Path(args.out).stem if Path(args.out).suffix else "presence"
    ex = export(str(master), str(outdir), prov,
                formats=tuple(args.formats.split(",")), stem=stem)
    print(f"export: {ex.master_wav}" + (f" (+mp3/m4a)" if ex.mp3 else ""))
    print(f"provenance sidecar: {ex.sidecar}")
    print(f"done in {elapsed:.1f}s")
    return 0


def _cmd_sidecar(args) -> int:
    from .api import run_server
    run_server(port=args.port)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="presence", description=f"{APP_NAME} CLI")
    ap.add_argument("--version", action="version", version=f"{APP_NAME} {APP_VERSION}")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("presets", help="list shipped voice-design presets")
    p.set_defaults(func=_cmd_presets)

    g = sub.add_parser("generate", help="text -> speech -> design -> export")
    g.add_argument("script", help="text or path to .md/.txt")
    g.add_argument("--engine", default=SETTINGS.default_engine)
    g.add_argument("--design", default=SETTINGS.default_design)
    g.add_argument("--lufs", type=float, default=None, help="override target (e.g. -23)")
    g.add_argument("--reference", help="path to your own-voice reference wav")
    g.add_argument("--transcript", default="", help="reference transcript")
    g.add_argument("--seed", type=int, default=1234)
    g.add_argument("--out", default="presence-export")
    g.add_argument("--formats", default="wav,mp3,m4a")
    g.add_argument("--no-check", action="store_true",
                   help="skip the per-segment WER self-check (not recommended)")
    g.set_defaults(func=_cmd_generate)

    s = sub.add_parser("sidecar", help="start the local API server")
    s.add_argument("--port", type=int, default=8765)
    s.set_defaults(func=_cmd_sidecar)

    args = ap.parse_args()
    if not getattr(args, "cmd", None):
        ap.print_help()
        return 1
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
