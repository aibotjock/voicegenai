/**
 * Types for the sidecar API. Every shape here is derived from the actual
 * FastAPI responses in sidecar/presence_sidecar (api.py, jobs/manager.py,
 * profiles/capture_qc.py, export/writer.py, export/provenance.py).
 */

// -- GET /health (unauthenticated) ------------------------------------------

export interface HealthState {
  app: string;
  version: string;
  status: string;
  time: string;
  engines: EngineInfo[];
  presets: string[];
  default_engine: string;
  default_design: string;
}

// -- GET /api/v1/engines -----------------------------------------------------

export interface EngineInfo {
  id: string;
  model_id: string;
  languages: string[];
  test_only?: boolean;
  error?: string;
}

// -- GET /api/v1/presets -----------------------------------------------------

export interface PresetInfo {
  name: string;
  character: string;
  params_hash: string;
  lufs_target: number;
}
export type PresetsMap = Record<string, PresetInfo>;

// -- profiles ----------------------------------------------------------------

export interface VoiceProfile {
  id: string;
  name: string;
  status: string;
  created_at: string;
  capture_kind: string;
}

/** profiles/capture_qc.py → to_dict() */
export interface QCResult {
  duration_s: number;
  sample_rate: number;
  snr_db: number;
  clipping_events: number;
  max_abs: number;
  silence_ratio: number;
  multi_speaker_suspect: boolean;
  ok: boolean;
  issues: string[];
}

/** POST /api/v1/profiles — QC failures return HTTP 200 with ok:false. */
export type CreateProfileResult =
  | { ok: true; profile_id: string; qc: QCResult }
  | { ok: false; qc: QCResult; message: string };

/** DELETE /api/v1/profiles/{id} */
export interface DeleteProfileResult {
  ok: boolean;
  deleted: number;
  residual: number;
}

// -- generation ---------------------------------------------------------------

export interface GlossaryItem {
  term: string;
  phonemes?: string | null;
  say_as?: string | null;
  letter_form?: boolean;
}

/** POST /api/v1/generate request (api.py GenerateIn). */
export interface GenerateRequest {
  script: string;
  fmt?: string;
  profile_id: string;
  design: string;
  lufs?: number | null;
  engine?: string | null;
  seed?: number;
  check_wer?: boolean;
  glossary?: GlossaryItem[];
}

export interface GenerateResponse {
  job_id: string;
  status: JobStatus;
}

export type JobStatus = "queued" | "running" | "done" | "failed" | "cancelled";

export type SegmentStatus =
  | "pending"
  | "synthesizing"
  | "checking"
  | "flagged"
  | "done"
  | "failed";

/** jobs/manager.py SegmentState */
export interface GenerationSegment {
  index: number;
  text: string;
  spoken_text: string;
  status: SegmentStatus;
  wer: number | null;
  retries: number;
  wav_path: string;
  error: string;
}

/** jobs/manager.py result dict (present once the job finishes). */
export interface JobResult {
  segments?: number;
  flagged?: number;
  engine?: string;
  model_version?: string;
  design?: string;
  elapsed_s?: number;
}

/** GET /api/v1/jobs/{id} → GenerationJob.snapshot() */
export interface GenerationJob {
  id: string;
  status: JobStatus;
  created_at: string;
  segments: GenerationSegment[];
  error: string;
  result: JobResult;
}

// -- SSE events (GET /api/v1/jobs/{id}/events) --------------------------------

export type JobSseEvent =
  | { kind: "open" }
  | { kind: "prepared"; segments: number }
  | { kind: "segment"; index: number; status: SegmentStatus; wer: number | null; retries: number }
  | { kind: "retry"; index: number; attempt: number; wer: number }
  | { kind: "done"; result: JobResult }
  | { kind: "failed"; error: string }
  | { kind: "cancelled" };

// -- export -------------------------------------------------------------------

/** export/provenance.py Provenance.to_dict() */
export interface Provenance {
  app: string;
  app_version: string;
  synthetic: boolean;
  synthetic_flag: string;
  engine_id: string;
  engine_version: string;
  model_id: string;
  model_version: string;
  design_id: string;
  design_name: string;
  design_params_hash: string;
  seed: number | null;
  script_sha256: string;
  generated_at: string;
  loudness: Record<string, number>;
  layers: Record<string, string>;
}

export interface LoudnessSummary {
  integrated_lufs: number;
  true_peak_db: number;
  lra_lu: number;
}

/** POST /api/v1/jobs/{id}/export request (api.py ExportIn). */
export interface ExportRequest {
  formats: string; // comma-separated: "wav", "wav,mp3", ...
  stem: string;
}

/** POST export response (jobs/manager.py GenerationJob.export). */
export interface ExportResult {
  ok: boolean;
  master: string;
  mp3: string | null;
  m4a: string | null;
  sidecar: string;
  loudness: LoudnessSummary;
  provenance: Provenance;
}

// -- audit / diagnostics -------------------------------------------------------

/** audit.py append_event payload. */
export interface AuditEvent {
  ts: string;
  event: string;
  profile_id: string | null;
  design_id: string | null;
  engine_id: string | null;
  text_sha256: string | null;
  duration_s: number | null;
  detail: string | null;
}

export interface DiagnosticsBundle {
  bundle: string; // JSON string: config + logs, no audio/voiceprints
}

// -- library (shell-level, not a backend route) -------------------------------

/** A file listed from the local exports directory (Tauri fs / dev middleware). */
export interface ExportFile {
  name: string;
  path: string;
  size: number;
  modified: string;
}
