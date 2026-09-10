/**
 * Raw JSON payloads arriving over the SSE events route, before narrowing
 * into the app's typed event model. Field presence depends on `event`.
 */
import type { JobResult, SegmentStatus } from "./types";

export interface RawJobEventPayload {
  event?: "prepared" | "done" | "failed" | "cancelled" | "segment" | "retry";
  segments?: number;
  result?: JobResult;
  error?: string;
  index?: number;
  attempt?: number;
  wer?: number | null;
  status?: SegmentStatus;
  retries?: number;
}
