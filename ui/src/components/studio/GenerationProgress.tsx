import { useMemo } from "react";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import type { GenerationJob } from "../../lib/api/types";
import { Progress, Spinner } from "../ui/Feedback";
import "./studio.css";

/**
 * Stage-based generation progress derived from real job state.
 * No fabricated percentages: the bar reflects completed sections out of
 * total sections, and the label names the actual stage.
 */
export function GenerationProgress({ job }: { job: GenerationJob }) {
  const stage = useMemo(() => describeStage(job), [job]);
  const done = job.segments.filter(
    (s) => s.status === "done" || s.status === "flagged",
  ).length;
  const total = job.segments.length;
  const pct = total > 0 ? (done / total) * 100 : job.status === "done" ? 100 : 0;

  return (
    <section className="gen-progress" aria-label="Generation progress" aria-live="polite">
      <div className="gen-stage">
        {job.status === "done" ? (
          <CheckCircle2 size={18} style={{ color: "var(--success)" }} aria-hidden="true" />
        ) : job.status === "failed" || job.status === "cancelled" ? (
          <AlertTriangle size={18} style={{ color: "var(--danger)" }} aria-hidden="true" />
        ) : (
          <Spinner />
        )}
        {stage}
      </div>
      {total > 0 ? <Progress value={pct} /> : null}
      <p className="gen-meta">
        {total > 0
          ? `${done} of ${total} sections finished`
          : job.status === "running" || job.status === "queued"
            ? "Starting…"
            : ""}
        {job.result.elapsed_s != null ? ` · took ${job.result.elapsed_s}s` : ""}
      </p>
      {job.status === "failed" && job.error ? (
        <p className="gen-meta" role="alert" style={{ color: "var(--danger)" }}>
          {job.error}
        </p>
      ) : null}
    </section>
  );
}

/** Human stage label from the live job — mirrors backend pipeline stages. */
export function describeStage(job: GenerationJob): string {
  switch (job.status) {
    case "queued":
      return "Preparing script";
    case "done":
      return "Ready";
    case "failed":
      return "Generation failed";
    case "cancelled":
      return "Cancelled";
    case "running":
      break;
  }
  if (job.segments.length === 0) return "Preparing script";
  const active = job.segments.find(
    (s) => s.status === "synthesizing" || s.status === "checking",
  );
  if (active) {
    const n = active.index + 1;
    if (active.status === "checking") {
      return active.retries > 0
        ? `Retrying section ${n} of ${job.segments.length}`
        : `Checking accuracy of section ${n} of ${job.segments.length}`;
    }
    return `Generating section ${n} of ${job.segments.length}`;
  }
  const allSettled = job.segments.every(
    (s) => s.status === "done" || s.status === "flagged" || s.status === "failed",
  );
  return allSettled ? "Processing voice style" : "Preparing script";
}
