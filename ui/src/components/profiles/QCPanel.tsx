import { CheckCircle2, AlertTriangle } from "lucide-react";
import type { QCResult } from "../../lib/api/types";
import {
  QC_VERDICT_LABEL,
  qcChecks,
  qcVerdict,
} from "../../lib/qcView";
import { Badge } from "../ui/Badge";
import { Collapsible } from "../ui/Collapsible";
import "./profiles.css";

/**
 * Recording-check feedback: friendly verdict + per-check rows.
 * Numbers stay available behind Details; nothing is fabricated — every row
 * maps directly to a backend QC field.
 */
export function QCPanel({ qc }: { qc: QCResult }) {
  const verdict = qcVerdict(qc);
  const checks = qcChecks(qc);
  return (
    <section className="qc-panel" aria-label="Recording check results">
      <div className="qc-head">
        <h3 className="qc-title">Recording check</h3>
        <Badge
          tone={
            verdict === "needs-improvement"
              ? "warning"
              : verdict === "excellent"
                ? "success"
                : "info"
          }
          dot
        >
          {QC_VERDICT_LABEL[verdict]}
        </Badge>
      </div>

      <ul className="qc-checks">
        {checks.map((c) => (
          <li key={c.id} className="qc-check">
            {c.passed ? (
              <CheckCircle2 size={16} className="qc-check-icon qc-check-pass" aria-hidden="true" />
            ) : (
              <AlertTriangle size={16} className="qc-check-icon qc-check-fail" aria-hidden="true" />
            )}
            <span>
              <span className="qc-check-label">{c.label}: </span>
              <span className="qc-check-detail">{c.detail}</span>
            </span>
          </li>
        ))}
      </ul>

      {qc.issues.length > 0 ? (
        <div className="qc-issues">
          {qc.issues.map((issue, i) => (
            <p key={i} className="qc-issue">
              {issue}
            </p>
          ))}
        </div>
      ) : null}

      <Collapsible title="Technical details">
        <p className="qc-technical">
          {[
            `duration_s: ${qc.duration_s}`,
            `sample_rate: ${qc.sample_rate}`,
            `snr_db: ${qc.snr_db}`,
            `clipping_events: ${qc.clipping_events}`,
            `silence_ratio: ${qc.silence_ratio}`,
            `multi_speaker_suspect: ${qc.multi_speaker_suspect}`,
          ].join("\n")}
        </p>
      </Collapsible>
    </section>
  );
}
