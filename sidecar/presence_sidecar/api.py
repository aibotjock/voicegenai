"""Presence Studio sidecar API.

Security (spec §5/§9): binds 127.0.0.1 ONLY, per-launch random bearer token
(never a LAN interface), one process/one lifecycle/one health endpoint.
The shell app receives the token via the launch line printed on stdout.

Routes (v1):
  GET  /health                      liveness + engine/preset info (no auth)
  GET  /api/v1/engines              available engines
  GET  /api/v1/presets              shipped voice-design presets
  POST /api/v1/profiles             create profile (multipart: capture audio)
  GET  /api/v1/profiles             list profiles (no voiceprint material)
  DELETE /api/v1/profiles/{id}      "Delete my voice" (verified wipe)
  POST /api/v1/generate             start a generation job
  GET  /api/v1/jobs/{id}           job state (segments, WER flags)
  GET  /api/v1/jobs/{id}/events    SSE stream of job progress
  POST /api/v1/jobs/{id}/export    export a completed job (wav/mp3/m4a)
  GET  /api/v1/audit               local audit log (hashes only)
  GET  /api/v1/diagnostics          logs+config bundle (no audio/voiceprints)

Zero egress in local mode: no route performs any network call; the cloud
engine option (P1) does not exist in this build by design.
"""
from __future__ import annotations

import datetime as _dt
import secrets
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import APP_NAME, APP_VERSION, audit
from .config import SETTINGS
from .dsp import PRESETS, get_preset
from .text_pipeline import prepare_script
from .text_pipeline.glossary import Pronunciation
from .profiles.store import ProfileStore
from .profiles.capture_qc import qc as capture_qc, to_dict as qc_dict

# ---------------------------------------------------------------------------
# Request models (module level: with postponed annotations FastAPI resolves
# type hints from module globals — models defined inside the factory are
# invisible to it and degrade to query params)
# ---------------------------------------------------------------------------


class GlossaryIn(BaseModel):
    term: str
    phonemes: str | None = None
    say_as: str | None = None
    letter_form: bool = False


class GenerateIn(BaseModel):
    script: str
    fmt: str = "text"
    profile_id: str
    design: str = "podcast"
    lufs: float | None = None
    engine: str | None = None
    seed: int = 1234
    check_wer: bool = True
    glossary: list[GlossaryIn] = Field(default_factory=list)


class ExportIn(BaseModel):
    formats: str = "wav,mp3,m4a"
    stem: str = "presence-export"


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(token: str | None = None) -> FastAPI:
    app = FastAPI(title=f"{APP_NAME} sidecar", version=APP_VERSION)
    # per-launch random bearer token (127.0.0.1 only); exposed on app.state
    # so the shell handshake can print it without burying it in closures
    app.state.presence_token = token or secrets.token_urlsafe(32)
    state = {
        "jobs": {},           # job_id -> GenerationJob
        "store": None,
    }

    def store() -> ProfileStore:
        if state["store"] is None:
            state["store"] = ProfileStore()
        return state["store"]

    def require_token(authorization: str = Header(default="")) -> None:
        # per-launch random bearer token; binds 127.0.0.1 only
        expected = f"Bearer {app.state.presence_token}"
        if authorization != expected:
            raise HTTPException(status_code=401, detail="invalid sidecar token")

    # -- health ------------------------------------------------------------

    @app.get("/health")
    def health() -> dict:
        from .engines import available_engines
        return {
            "app": APP_NAME, "version": APP_VERSION, "status": "ok",
            "time": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "engines": [e for e in available_engines() if not e.get("test_only")],
            "presets": sorted(PRESETS),
            "default_engine": SETTINGS.default_engine,
            "default_design": SETTINGS.default_design,
        }

    # -- presets / engines ----------------------------------------------------

    @app.get("/api/v1/presets", dependencies=[Depends(require_token)])
    def presets() -> dict:
        return {
            pid: {"name": p.name, "character": p.character,
                  "params_hash": p.params_hash(),
                  "lufs_target": p.lufs_target}
            for pid, p in PRESETS.items()
        }

    @app.get("/api/v1/engines", dependencies=[Depends(require_token)])
    def engines() -> list[dict]:
        from .engines import available_engines
        return available_engines()

    # -- profiles -------------------------------------------------------------

    @app.post("/api/v1/profiles", dependencies=[Depends(require_token)])
    def create_profile(
        name: str = Form(...),
        capture_kind: str = Form("guided"),
        capture: UploadFile = File(...),
    ) -> dict:
        data = capture.file.read()
        pid = store().create_profile(name, capture_kind)
        tmp = Path(SETTINGS.audio_dir) / f"upload-{uuid.uuid4().hex}.wav"
        tmp.write_bytes(data)
        result = capture_qc(str(tmp))
        if not result.ok:
            # QC gate: capture refused with plain-language feedback
            tmp.unlink(missing_ok=True)
            store().delete_my_voice(pid)
            return {"ok": False, "qc": qc_dict(result),
                    "message": "Recording did not pass quality checks."}
        store().add_reference(
            pid, "capture", data, transcript="",
            duration_s=result.duration_s, snr_db=result.snr_db,
        )
        audit.append_event("profile-create", profile_id=pid,
                           detail=f"capture_kind={capture_kind}")
        return {"ok": True, "profile_id": pid, "qc": qc_dict(result)}

    @app.get("/api/v1/profiles", dependencies=[Depends(require_token)])
    def list_profiles() -> list[dict]:
        return [
            {"id": p["id"], "name": p["name"], "status": p["status"],
             "created_at": p["created_at"], "capture_kind": p["capture_kind"]}
            for p in store().list_profiles()
        ]

    @app.delete("/api/v1/profiles/{pid}", dependencies=[Depends(require_token)])
    def delete_profile(pid: str) -> dict:
        """Delete my voice: one click, instant, verifiable wipe."""
        res = store().delete_my_voice(pid)
        audit.append_event("profile-delete", profile_id=pid,
                           detail=f"ok={res['ok']} residual={len(res['residual'])}")
        if not res["ok"]:
            raise HTTPException(400, "delete failed — residual files remain")
        return {"ok": True, "deleted": len(res["deleted"]), "residual": 0}

    # -- generation jobs ---------------------------------------------------

    @app.post("/api/v1/generate", dependencies=[Depends(require_token)])
    def generate(req: GenerateIn) -> dict:
        from .jobs.manager import start_job
        job = start_job(store(), req.model_dump(), state["jobs"])
        return {"job_id": job.id, "status": job.status}

    @app.get("/api/v1/jobs/{job_id}", dependencies=[Depends(require_token)])
    def job_state(job_id: str) -> dict:
        job = state["jobs"].get(job_id)
        if job is None:
            raise HTTPException(404, "job not found")
        return job.snapshot()

    @app.get("/api/v1/jobs/{job_id}/events")
    def job_events(job_id: str):
        job = state["jobs"].get(job_id)
        if job is None:
            raise HTTPException(404, "job not found")
        return StreamingResponse(job.event_stream(), media_type="text/event-stream")

    @app.post("/api/v1/jobs/{job_id}/export", dependencies=[Depends(require_token)])
    def job_export(job_id: str, req: ExportIn) -> dict:
        from .jobs.manager import export_job
        try:
            out = export_job(state["jobs"][job_id], req.formats, req.stem)
        except KeyError:
            raise HTTPException(404, "job not found")
        except RuntimeError as e:
            raise HTTPException(409, str(e))
        audit.append_event("export", detail=f"job={job_id} formats={req.formats}")
        return out

    # -- audit / diagnostics --------------------------------------------------

    @app.get("/api/v1/audit", dependencies=[Depends(require_token)])
    def audit_log() -> list[dict]:
        return audit.read_events()

    @app.get("/api/v1/diagnostics", dependencies=[Depends(require_token)])
    def diagnostics() -> dict:
        return {"bundle": audit.diagnostics_bundle()}

    return app


# ---------------------------------------------------------------------------
# Server entry (called by `presence sidecar` / `presence-sidecar`)
# ---------------------------------------------------------------------------


def run_server(port: int = 8765) -> None:
    import uvicorn

    app = create_app()
    # launch handshake line for the shell app to consume (token + port)
    print(f"PRESENCE_SIDECAR_READY token={app.state.presence_token} port={port}",
          flush=True)
    cfg = uvicorn.Config(app, host=SETTINGS.host, port=port, log_level="warning")
    server = uvicorn.Server(cfg)
    server.run()
