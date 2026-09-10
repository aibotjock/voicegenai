import { useState } from "react";
import { Download, ShieldCheck } from "lucide-react";
import type { ExportResult, GenerationJob } from "../../lib/api/types";
import { formatDuration } from "../../lib/format";
import { AudioPlayer } from "../audio/AudioPlayer";
import { useAudioFile } from "../audio/useAudioFile";
import { Button } from "../ui/Button";
import { Spinner } from "../ui/Feedback";
import { ExportDialog } from "./ExportDialog";
import { engineDisplayName } from "./AdvancedPanel";
import "./studio.css";

interface OutputPanelProps {
  job: GenerationJob;
  /** WAV preview export (auto-created when the job finished). */
  preview: ExportResult | null;
  previewLoading: boolean;
  /** Latest explicit export (may equal preview). */
  lastExport: ExportResult | null;
  onExported: (result: ExportResult) => void;
}

/**
 * Output region: the generated audio lands here automatically (loaded into
 * the player, not autoplayed), with loudness summary, provenance status and
 * the Export action.
 */
export function OutputPanel({ job, preview, previewLoading, lastExport, onExported }: OutputPanelProps) {
  const [exportOpen, setExportOpen] = useState(false);
  const audio = useAudioFile(preview?.master ?? null);
  const summary = lastExport ?? preview;

  return (
    <section className="output-panel" aria-label="Output">
      <h2 className="section-title">Output</h2>

      {previewLoading ? (
        <div className="player" aria-label="Preparing audio">
          <div style={{ display: "flex", gap: 8, alignItems: "center", color: "var(--text-2)" }}>
            <Spinner /> Preparing your audio…
          </div>
        </div>
      ) : audio.status === "ready" && audio.audio ? (
        <AudioPlayer
          src={audio.audio.url}
          peaks={audio.audio.peaks}
          durationS={audio.audio.durationS}
          title={`${job.result.design ?? "Voice"} · ${audio.audio.durationS ? formatDuration(audio.audio.durationS) : ""}`}
        />
      ) : audio.status === "error" ? (
        <div className="player">
          <p className="gen-meta" role="alert">
            The audio was generated but could not be loaded for playback here. Use Export to
            save it to a file.
          </p>
        </div>
      ) : null}

      {summary ? (
        <div className="output-summary">
          <span>
            Style: <strong>{summary.provenance.design_name}</strong>
          </span>
          <span>
            Engine: <strong>{engineDisplayName(summary.provenance.engine_id)}</strong>
          </span>
          <span>
            Loudness: <strong>{summary.loudness.integrated_lufs} LUFS</strong> (peak{" "}
            {summary.loudness.true_peak_db} dB)
          </span>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
            <ShieldCheck size={14} style={{ color: "var(--success)" }} aria-hidden="true" />
            Synthetic provenance included
          </span>
        </div>
      ) : null}

      <div>
        <Button variant="primary" onClick={() => setExportOpen(true)}>
          <Download size={15} aria-hidden="true" /> Export
        </Button>
      </div>

      {lastExport ? <ExportSuccessCard result={lastExport} /> : null}

      <ExportDialog
        jobId={job.id}
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        onExported={onExported}
      />
    </section>
  );
}

function ExportSuccessCard({ result }: { result: ExportResult }) {
  const files = [result.master, result.mp3, result.m4a].filter(Boolean) as string[];
  return (
    <div className="export-result" role="status">
      <strong>Export complete</strong>
      <div className="export-files">
        {files.map((f) => (
          <div key={f}>{f}</div>
        ))}
      </div>
      <span className="gen-meta">
        {result.loudness.integrated_lufs} LUFS integrated · true peak {result.loudness.true_peak_db}{" "}
        dB · provenance embedded + sidecar JSON
      </span>
    </div>
  );
}
