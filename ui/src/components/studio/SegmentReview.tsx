import { AlertTriangle, CheckCircle2 } from "lucide-react";
import type { GenerationJob } from "../../lib/api/types";
import { Badge } from "../ui/Badge";
import { Collapsible } from "../ui/Collapsible";
import "./studio.css";

interface SegmentReviewProps {
  job: GenerationJob;
}

/**
 * Section quality review. Normal users see a summary count; flagged
 * sections are listed with intended text, status and retry count, with
 * technical detail (WER) behind an expander. Flags are never hidden and
 * never overstated.
 */
export function SegmentReview({ job }: SegmentReviewProps) {
  if (job.segments.length === 0) return null;
  const flagged = job.segments.filter((s) => s.status === "flagged");
  const failed = job.segments.filter((s) => s.status === "failed");
  const done = job.segments.filter((s) => s.status === "done");
  const finished = job.status === "done" || job.status === "failed";

  if (!finished && flagged.length === 0 && failed.length === 0) return null;

  const headline =
    flagged.length === 0 && failed.length === 0
      ? `${done.length} ${done.length === 1 ? "section" : "sections"} generated successfully.`
      : `${job.segments.length} sections generated. ${flagged.length + failed.length} need${
          flagged.length + failed.length === 1 ? "s" : ""
        } review.`;

  return (
    <section className="review-panel" aria-label="Section review">
      <div className="review-item-head">
        <h3 className="qc-title" style={{ fontSize: "var(--text-md)" }}>
          Section review
        </h3>
        {flagged.length === 0 && failed.length === 0 ? (
          <Badge tone="success" dot>
            All sections passed
          </Badge>
        ) : (
          <Badge tone="warning" dot>
            {flagged.length + failed.length} to review
          </Badge>
        )}
      </div>
      <p className="gen-meta">{headline}</p>

      {[...flagged, ...failed].map((s) => (
        <div key={s.index} className="review-item">
          <div className="review-item-head">
            <span style={{ fontWeight: 600 }}>Section {s.index + 1}</span>
            <Badge tone={s.status === "failed" ? "danger" : "warning"} dot>
              {s.status === "failed" ? "Failed" : "Needs review"}
            </Badge>
          </div>
          <p className="review-text">“{s.text}”</p>
          <p className="gen-meta">
            {s.status === "failed"
              ? "This section could not be generated."
              : "The accuracy check was not confident about this section."}
            {s.retries > 0
              ? ` Retried automatically ${s.retries} ${s.retries === 1 ? "time" : "times"}.`
              : ""}
          </p>
          <Collapsible title="Technical details">
            <p className="qc-technical">
              {[
                `status: ${s.status}`,
                `wer: ${s.wer ?? "n/a"}`,
                `retries: ${s.retries}`,
                s.error ? `error: ${s.error}` : "",
              ]
                .filter(Boolean)
                .join("\n")}
            </p>
          </Collapsible>
        </div>
      ))}

      {flagged.length > 0 && finished ? (
        <p className="gen-meta" role="note">
          <CheckCircle2 size={13} aria-hidden="true" style={{ verticalAlign: "-2px" }} /> Flagged
          sections are still included in the export — listen to them and regenerate with a
          different seed if a line sounds off.{" "}
          <AlertTriangle size={13} aria-hidden="true" style={{ verticalAlign: "-2px" }} />
        </p>
      ) : null}
    </section>
  );
}
