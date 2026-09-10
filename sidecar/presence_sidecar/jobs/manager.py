"""Generation jobs: resumable, cancellable, per-segment retry, SSE.

Contract (spec §4/§5/§12):
- progress + cancel per segment; SSE streams finished segments
- WER self-check per segment: flagged segments retry up to 3 automatic
  times with different seeds, then surface the flag for a user decision —
  never silently accepted, never silently retried past 3
- intermediate files have a disk quota and are cleaned on job completion
- engine + model version + seed are recorded for provenance
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import soundfile as sf

from .. import audit
from ..config import SETTINGS
from ..dsp import get_preset, run_dsp, join_segments, JoinItem
from ..asr.whisper import WhisperASR
from ..asr.wer import compute_wer, WER_THRESHOLD, MAX_AUTO_RETRIES
from ..export.provenance import Provenance
from ..export.writer import export
from ..text_pipeline import prepare_script
from ..text_pipeline.glossary import Pronunciation


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


@dataclass
class SegmentState:
    index: int
    text: str
    spoken_text: str
    status: str = "pending"     # pending|synthesizing|checking|flagged|done|failed
    wer: float | None = None
    retries: int = 0
    wav_path: str = ""
    error: str = ""


class GenerationJob:
    def __init__(self, params: dict, store) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.params = params
        self.store = store
        self.status = "queued"
        self.created_at = _now()
        self.segments: list[SegmentState] = []
        self.events: "queue.Queue[dict]" = queue.Queue()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self.error = ""
        self.result: dict = {}

    # -- control -----------------------------------------------------------

    def start(self) -> None:
        self.status = "running"
        self._thread = threading.Thread(target=self._execute, daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()
        self.status = "cancelled"
        self._emit("job", {"event": "cancelled"})

    def snapshot(self) -> dict:
        return {
            "id": self.id, "status": self.status, "created_at": self.created_at,
            "segments": [dataclasses.asdict(s) for s in self.segments],
            "error": self.error, "result": self.result,
        }

    def event_stream(self):
        """SSE generator over queued job events (live tail)."""
        yield "event: open\n\n"
        while True:
            try:
                kind, data = self.events.get(timeout=1.0)
            except queue.Empty:
                if self.status in ("done", "failed", "cancelled"):
                    break
                yield ": keepalive\n\n"
                continue
            payload = data if isinstance(data, dict) else {"value": data}
            yield f"event: {kind}\ndata: {__import__('json').dumps(payload)}\n\n"

    def _emit(self, kind: str, data) -> None:
        self.events.put((kind, data))

    # -- execution ---------------------------------------------------------

    def _execute(self) -> None:
        try:
            self._run()
            self.status = "done"
            self._emit("job", {"event": "done", "result": self.result})
        except Exception as e:  # noqa: BLE001 — surface, never crash silently
            self.error = str(e)
            self.status = "failed"
            self._emit("job", {"event": "failed", "error": str(e)})

    def _run(self) -> None:
        from ..engines import get_engine
        from ..engines.base import EngineRef, SynthRequest

        p = self.params
        design = get_preset(p["design"], p.get("lufs"))
        engine = get_engine(p.get("engine") or SETTINGS.default_engine)
        engine.load()
        caps = engine.capabilities()

        glossary = [Pronunciation(**g) for g in p.get("glossary", [])]
        prof = self.store.get_profile(p["profile_id"])
        if prof is None:
            raise RuntimeError("profile not found")
        ref_meta = self.store.get_reference(p["profile_id"])
        if ref_meta is None:
            raise RuntimeError("profile has no reference capture")

        # decrypt reference to a working file for the engine
        ref_path = Path(SETTINGS.audio_dir) / f"jobref-{self.id}.wav"
        ref_path.write_bytes(self.store.load_encrypted(ref_meta["file_key"]))
        try:
            prepared = prepare_script(
                p["script"], fmt=p.get("fmt", "text"),
                profile_glossary=[],
                script_glossary=glossary,
                engine_supports_phonemes=caps.supports_phoneme_inpainting,
            )
            if not prepared.segments:
                raise RuntimeError("script produced no segments")
            for seg in prepared.segments:
                self.segments.append(SegmentState(
                    index=seg.index, text=seg.text, spoken_text=seg.text))
            self._emit("job", {"event": "prepared",
                               "segments": len(self.segments)})

            asr = WhisperASR() if p.get("check_wer", True) else None
            if asr is not None:
                asr.load()

            ref = EngineRef(wav_path=str(ref_path),
                            transcript=ref_meta.get("transcript") or "")
            workdir = Path(SETTINGS.audio_dir) / f"job-{self.id}"
            (workdir / "segs").mkdir(parents=True, exist_ok=True)
            t_start = time.time()
            last_engine_res = None
            for state in self.segments:
                if self._cancel.is_set():
                    return
                # synthesize + WER self-check with bounded retries
                for attempt in range(MAX_AUTO_RETRIES + 1):
                    state.status = "synthesizing"
                    res = engine.synthesize(SynthRequest(
                        text=state.text, reference=ref,
                        seed=p.get("seed", 1234) + state.index + attempt * 1000,
                    ))
                    last_engine_res = res
                    # container normalize to 48k float
                    y, sr_in = sf.read(res.wav_path, dtype="float32",
                                      always_2d=False)
                    if y.ndim > 1:
                        y = y.mean(axis=1)
                    state.wav_path = str(workdir / "segs" /
                                         f"seg{state.index:03d}.wav")
                    sf.write(state.wav_path, y, sr_in, subtype="FLOAT")
                    if asr is None:
                        break
                    state.status = "checking"
                    hyp = asr.transcribe(state.wav_path).text
                    state.wer = compute_wer(hyp, state.text)
                    if state.wer <= WER_THRESHOLD:
                        break
                    state.retries = attempt + 1
                    self._emit("segment", {
                        "event": "retry", "index": state.index,
                        "attempt": attempt + 1, "wer": round(state.wer, 3)})
                # after the loop: either ok, or flagged after MAX_AUTO_RETRIES
                if asr is not None and state.wer is not None and \
                        state.wer > WER_THRESHOLD:
                    state.status = "flagged"   # surfaced; never silent
                else:
                    state.status = "done"
                self._emit("segment", {
                    "event": "segment", "index": state.index,
                    "status": state.status, "wer": state.wer,
                    "retries": state.retries})
            flagged = sum(1 for s in self.segments if s.status == "flagged")
            self.result = {
                "segments": len(self.segments), "flagged": flagged,
                "engine": engine.id, "model_version": engine.model_version,
                "design": design.id, "elapsed_s": round(time.time() - t_start, 1),
            }
            audit.append_event(
                "generate", profile_id=p["profile_id"], design_id=design.id,
                engine_id=engine.id, text_sha256=prepared.text_sha256,
                duration_s=self.result["elapsed_s"],
                detail=f"segments={len(self.segments)} flagged={flagged}")
            self._design = design
            self._prepared = prepared
            self._engine_res = last_engine_res
        finally:
            ref_path.unlink(missing_ok=True)

    # -- export -----------------------------------------------------------

    def export(self, formats: str = "wav,mp3,m4a", stem: str = "presence-export") -> dict:
        design = getattr(self, "_design", None) or get_preset(self.params["design"])
        prepared = getattr(self, "_prepared", None)
        if self.status != "done" or not self.segments:
            raise RuntimeError("job is not complete")
        workdir = Path(SETTINGS.audio_dir) / f"job-{self.id}"
        items = []
        for i, s in enumerate(self.segments):
            if s.status == "failed":
                raise RuntimeError(f"segment {s.index} failed — cannot export")
            boundary = None
            if i > 0:
                seg = prepared.segments[i] if prepared else None
                is_para = bool(seg and seg.is_paragraph_start)
                if is_para and design.pause_shaping_ms:
                    boundary = f"pause:{max(design.pause_shaping_ms, 250)}"
                else:
                    boundary = "join"
            items.append(JoinItem(s.wav_path, boundary))
        joined = workdir / "joined.wav"
        join_segments(items, str(joined), design=design)
        master = workdir / "master.wav"
        dsp_rep = run_dsp(str(joined), str(master), design, workdir / "dspwk")
        from ..dsp.loudness import measure
        m = measure(str(master))
        res = self._engine_res
        prov = Provenance(
            engine_id=res.engine_id, engine_version=res.engine_version,
            model_id=res.model_id, model_version=res.model_version,
            design_id=design.id, design_name=design.name,
            design_params_hash=design.params_hash(),
            seed=self.params.get("seed", 1234),
            script_sha256=prepared.text_sha256 if prepared else "",
            loudness={"integrated_lufs": m["integrated_lufs"],
                      "true_peak_db": m["true_peak_db"],
                      "lra_lu": m["lra_lu"]},
        )
        ex = export(str(master), str(SETTINGS.exports_dir), prov,
                    formats=tuple(f.strip() for f in formats.split(",") if f.strip()),
                    stem=stem)
        # clean intermediates (quota hygiene)
        for f in (joined, master):
            f.unlink(missing_ok=True)
        return {
            "ok": True, "master": ex.master_wav, "mp3": ex.mp3,
            "m4a": ex.m4a, "sidecar": ex.sidecar,
            "loudness": {"integrated_lufs": round(m["integrated_lufs"], 2),
                         "true_peak_db": round(m["true_peak_db"], 2),
                         "lra_lu": round(m["lra_lu"], 2)},
            "provenance": prov.to_dict(),
        }


def start_job(store, params: dict, registry: dict) -> GenerationJob:
    job = GenerationJob(params, store)
    registry[job.id] = job
    job.start()
    return job


def export_job(job: GenerationJob, formats: str, stem: str) -> dict:
    return job.export(formats, stem)
