/**
 * React Query hooks for the sidecar API. Server truth lives here; components
 * read through these hooks instead of holding duplicate copies.
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";
import { useEffect, useReducer } from "react";
import { useApp } from "../state/AppContext";
import type { RawJobEventPayload } from "./typesInternal";
import type {
  AuditEvent,
  CreateProfileResult,
  DiagnosticsBundle,
  EngineInfo,
  ExportRequest,
  GenerateRequest,
  GenerateResponse,
  GenerationJob,
  HealthState,
  JobResult,
  PresetsMap,
  VoiceProfile,
} from "./types";

export const qk = {
  health: ["health"] as const,
  engines: ["engines"] as const,
  presets: ["presets"] as const,
  profiles: ["profiles"] as const,
  audit: ["audit"] as const,
  diagnostics: ["diagnostics"] as const,
};

function useClient() {
  const { client } = useApp();
  return client;
}

const readyOnly = (client: unknown) => client != null;

export function useHealth(options?: Partial<UseQueryOptions<HealthState>>) {
  const client = useClient();
  return useQuery({
    queryKey: qk.health,
    queryFn: () => client!.health(),
    enabled: readyOnly(client),
    refetchInterval: 30_000,
    retry: 1,
    ...options,
  });
}

export function useEngines() {
  const client = useClient();
  return useQuery<EngineInfo[]>({
    queryKey: qk.engines,
    queryFn: () => client!.engines(),
    enabled: readyOnly(client),
    staleTime: 60_000,
  });
}

export function usePresets() {
  const client = useClient();
  return useQuery<PresetsMap>({
    queryKey: qk.presets,
    queryFn: () => client!.presets(),
    enabled: readyOnly(client),
    staleTime: 60_000,
  });
}

export function useProfiles() {
  const client = useClient();
  return useQuery<VoiceProfile[]>({
    queryKey: qk.profiles,
    queryFn: () => client!.profiles(),
    enabled: readyOnly(client),
  });
}

export function useCreateProfile() {
  const client = useClient();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: {
      name: string;
      captureKind: "guided" | "upload";
      audio: Blob;
      filename?: string;
    }) =>
      client!.createProfile(args.name, args.captureKind, args.audio, args.filename) as Promise<CreateProfileResult>,
    onSuccess: (result) => {
      if (result.ok) void qc.invalidateQueries({ queryKey: qk.profiles });
    },
  });
}

export function useDeleteProfile() {
  const client = useClient();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => client!.deleteProfile(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.profiles }),
  });
}

export function useGenerate() {
  const client = useClient();
  return useMutation({
    mutationFn: (req: GenerateRequest) =>
      client!.generate(req) as Promise<GenerateResponse>,
  });
}

export function useExportJob() {
  const client = useClient();
  return useMutation({
    mutationFn: (args: { jobId: string; req: ExportRequest }) =>
      client!.exportJob(args.jobId, args.req),
  });
}

export function useAudit(enabled = true) {
  const client = useClient();
  return useQuery<AuditEvent[]>({
    queryKey: qk.audit,
    queryFn: () => client!.audit(),
    enabled: readyOnly(client) && enabled,
  });
}

export function useDiagnostics(enabled = true) {
  const client = useClient();
  return useQuery<DiagnosticsBundle>({
    queryKey: qk.diagnostics,
    queryFn: () => client!.diagnostics(),
    enabled: readyOnly(client) && enabled,
  });
}

// -- live job tracking (SSE, not polling) ------------------------------------

type JobViewAction =
  | { type: "snapshot"; job: GenerationJob }
  | { type: "prepared"; segments: number }
  | { type: "segment"; index: number; status: string; wer: number | null; retries: number }
  | { type: "retry"; index: number; attempt: number; wer: number }
  | { type: "done"; result: JobResult }
  | { type: "failed"; error: string }
  | { type: "cancelled" };

const TERMINAL = new Set(["done", "failed", "cancelled"]);

function jobViewReducer(state: GenerationJob | null, action: JobViewAction): GenerationJob | null {
  switch (action.type) {
    case "snapshot":
      // Never let a stale in-flight snapshot downgrade a terminal state.
      if (state && TERMINAL.has(state.status) && !TERMINAL.has(action.job.status)) {
        return state;
      }
      return action.job;
    case "prepared":
      // Segment list arrives via the snapshot refetch this triggers.
      return state;
    case "segment":
    case "retry": {
      if (!state) return state;
      const segments = state.segments.map((s) =>
        s.index === action.index
          ? {
              ...s,
              status: (action.type === "segment" ? action.status : "synthesizing") as GenerationJob["segments"][number]["status"],
              wer: action.wer ?? s.wer,
              retries: action.type === "retry" ? action.attempt : action.retries,
            }
          : s,
      );
      return { ...state, status: "running", segments };
    }
    case "done":
      return state ? { ...state, status: "done", result: action.result } : state;
    case "failed":
      return state ? { ...state, status: "failed", error: action.error } : state;
    case "cancelled":
      return state ? { ...state, status: "cancelled" } : state;
  }
}

/**
 * Track a generation job: one snapshot fetch + SSE for live updates.
 * No polling. Cleans up the subscription on unmount / job change.
 */
export function useGenerationJob(jobId: string | null) {
  const client = useClient();
  const [job, dispatch] = useReducer(jobViewReducer, null);

  useEffect(() => {
    if (!jobId || !client) return;
    let cancelled = false;
    let sub: { close: () => void } | null = null;

    const fetchSnapshot = async () => {
      try {
        const snap = await client.job(jobId);
        if (!cancelled) dispatch({ type: "snapshot", job: snap });
      } catch {
        /* surfaced via SSE failed event or offline pill */
      }
    };

    // Order matters: apply the snapshot BEFORE subscribing to the event
    // stream, so early SSE events always land on an initialized view. The
    // backend queues events server-side, so nothing is lost between the
    // snapshot fetch and the subscription.
    void (async () => {
      await fetchSnapshot();
      if (cancelled) return;
      sub = client.subscribeJobEvents(
      jobId,
      (msg) => {
        if (cancelled) return;
        const payload = safeJson(msg.data) as RawJobEventPayload | null;
        if (msg.event === "job" && payload) {
          switch (payload.event) {
            case "prepared":
              void fetchSnapshot(); // segment texts now available
              break;
            case "done":
              dispatch({ type: "done", result: payload.result ?? {} });
              // Final truth from the backend; reducer guards against staleness.
              void fetchSnapshot();
              break;
            case "failed":
              dispatch({ type: "failed", error: payload.error ?? "Generation failed" });
              break;
            case "cancelled":
              dispatch({ type: "cancelled" });
              break;
          }
        } else if (msg.event === "segment" && payload) {
          if (payload.event === "retry") {
            dispatch({
              type: "retry",
              index: payload.index ?? 0,
              attempt: payload.attempt ?? 0,
              wer: payload.wer ?? 0,
            });
          } else if (payload.event === "segment") {
            dispatch({
              type: "segment",
              index: payload.index ?? 0,
              status: payload.status ?? "pending",
              wer: payload.wer ?? null,
              retries: payload.retries ?? 0,
            });
          }
        }
      },
        () => {
          /* transport error — offline pill communicates state */
        },
      );
    })();

    return () => {
      cancelled = true;
      sub?.close();
    };
  }, [jobId, client]);

  return job;
}

function safeJson(text: string): unknown {
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return null;
  }
}
