/**
 * Typed client for the VoiceGenAI sidecar (Presence Studio FastAPI sidecar).
 *
 * - All routes live behind this one class; visual components never call
 *   fetch directly.
 * - The bearer token is injected per instance and kept only in memory.
 * - Transport is injectable: native fetch in browser dev (via Vite proxy),
 *   tauri-plugin-http in the desktop shell (the sidecar sends no CORS
 *   headers), a mock in tests.
 */
import { SidecarError } from "./errors";
import { subscribeSse, type RawSseMessage, type SseSubscription } from "./sse";
import type {
  AuditEvent,
  CreateProfileResult,
  DeleteProfileResult,
  DiagnosticsBundle,
  EngineInfo,
  ExportRequest,
  ExportResult,
  GenerateRequest,
  GenerateResponse,
  GenerationJob,
  HealthState,
  PresetsMap,
  VoiceProfile,
} from "./types";

export interface SidecarConnectionInfo {
  /** e.g. "http://127.0.0.1:8765" in desktop mode, "" (proxy) in dev. */
  baseUrl: string;
  token: string;
}

type FetchLike = typeof fetch;

export class SidecarClient {
  private readonly baseUrl: string;
  private readonly token: string;
  private readonly fetchImpl: FetchLike;

  constructor(conn: SidecarConnectionInfo, fetchImpl: FetchLike = fetch) {
    this.baseUrl = conn.baseUrl.replace(/\/$/, "");
    this.token = conn.token;
    // Wrap so the implementation is always invoked as a free function
    // (native fetch and tauri-plugin-http both work this way).
    this.fetchImpl = ((input: RequestInfo | URL, init?: RequestInit) =>
      fetchImpl(input, init)) as FetchLike;
  }

  private authHeaders(): Record<string, string> {
    return { Authorization: `Bearer ${this.token}` };
  }

  private async request<T>(
    path: string,
    init: RequestInit = {},
    opts: { auth?: boolean } = {},
  ): Promise<T> {
    const auth = opts.auth !== false;
    let res: Response;
    try {
      res = await this.fetchImpl(`${this.baseUrl}${path}`, {
        ...init,
        headers: {
          ...(auth ? this.authHeaders() : {}),
          ...(init.headers as Record<string, string> | undefined),
        },
      });
    } catch {
      throw new SidecarError(null, "network request failed");
    }
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const body = await res.json();
        if (typeof body?.detail === "string") detail = body.detail;
      } catch {
        /* non-JSON error body */
      }
      throw new SidecarError(res.status, detail);
    }
    return (await res.json()) as T;
  }

  // -- routes ---------------------------------------------------------------

  health(): Promise<HealthState> {
    return this.request<HealthState>("/health", {}, { auth: false });
  }

  engines(): Promise<EngineInfo[]> {
    return this.request<EngineInfo[]>("/api/v1/engines");
  }

  presets(): Promise<PresetsMap> {
    return this.request<PresetsMap>("/api/v1/presets");
  }

  profiles(): Promise<VoiceProfile[]> {
    return this.request<VoiceProfile[]>("/api/v1/profiles");
  }

  createProfile(
    name: string,
    captureKind: "guided" | "upload",
    audio: Blob,
    filename = "capture.wav",
  ): Promise<CreateProfileResult> {
    const form = new FormData();
    form.append("name", name);
    form.append("capture_kind", captureKind);
    form.append("capture", audio, filename);
    return this.request<CreateProfileResult>("/api/v1/profiles", {
      method: "POST",
      body: form,
    });
  }

  deleteProfile(id: string): Promise<DeleteProfileResult> {
    return this.request<DeleteProfileResult>(
      `/api/v1/profiles/${encodeURIComponent(id)}`,
      { method: "DELETE" },
    );
  }

  generate(req: GenerateRequest): Promise<GenerateResponse> {
    return this.request<GenerateResponse>("/api/v1/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });
  }

  job(jobId: string): Promise<GenerationJob> {
    return this.request<GenerationJob>(
      `/api/v1/jobs/${encodeURIComponent(jobId)}`,
    );
  }

  exportJob(jobId: string, req: ExportRequest): Promise<ExportResult> {
    return this.request<ExportResult>(
      `/api/v1/jobs/${encodeURIComponent(jobId)}/export`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      },
    );
  }

  audit(): Promise<AuditEvent[]> {
    return this.request<AuditEvent[]>("/api/v1/audit");
  }

  diagnostics(): Promise<DiagnosticsBundle> {
    return this.request<DiagnosticsBundle>("/api/v1/diagnostics");
  }

  /**
   * Subscribe to live job events (SSE). The sidecar's events route does not
   * require the token; we send it anyway so behavior is identical if that
   * changes. Returns an unsubscribe handle — callers must close on unmount.
   */
  subscribeJobEvents(
    jobId: string,
    onMessage: (msg: RawSseMessage) => void,
    onError?: (err: unknown) => void,
  ): SseSubscription {
    return subscribeSse(
      this.fetchImpl,
      `${this.baseUrl}/api/v1/jobs/${encodeURIComponent(jobId)}/events`,
      this.authHeaders(),
      onMessage,
      onError,
    );
  }
}
