import { useState } from "react";
import { friendlyError } from "../../lib/api/errors";
import { useExportJob } from "../../lib/api/hooks";
import type { ExportResult } from "../../lib/api/types";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Spinner } from "../ui/Feedback";
import "./studio.css";

const FORMATS = [
  { id: "wav", name: "Professional WAV", desc: "48 kHz / 24-bit master" },
  { id: "mp3", name: "MP3", desc: "320 kbps, universal" },
  { id: "m4a", name: "M4A", desc: "256 kbps AAC" },
] as const;

interface ExportDialogProps {
  jobId: string;
  open: boolean;
  onClose: () => void;
  onExported: (result: ExportResult) => void;
}

export function sanitizeStem(s: string): string {
  return s
    .trim()
    .replace(/[^\w\- ]+/g, "")
    .replace(/\s+/g, "-")
    .slice(0, 80);
}

/**
 * Export dialog: format cards, output name. Provenance is always embedded
 * by the backend — there is deliberately no toggle for it.
 */
export function ExportDialog({ jobId, open, onClose, onExported }: ExportDialogProps) {
  const exportJob = useExportJob();
  const [selected, setSelected] = useState<Set<string>>(new Set(["wav"]));
  const [stem, setStem] = useState("");
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const valid = selected.size > 0;
  const stemId = "export-stem";

  const doExport = async () => {
    setWorking(true);
    setError(null);
    try {
      const result = await exportJob.mutateAsync({
        jobId,
        req: {
          formats: [...selected].join(","),
          stem: sanitizeStem(stem) || `voicegen-${jobId}`,
        },
      });
      onExported(result);
      onClose();
    } catch (err) {
      setError(friendlyError(err, "Export failed."));
    } finally {
      setWorking(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={() => !working && onClose()}
      title="Export audio"
      actions={
        <>
          <Button variant="ghost" onClick={onClose} disabled={working}>
            Cancel
          </Button>
          <Button variant="primary" onClick={() => void doExport()} disabled={!valid || working}>
            {working ? <Spinner /> : null}
            Export
          </Button>
        </>
      }
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div>
          <p className="field-label" style={{ marginBottom: 8 }}>
            Formats
          </p>
          <div className="export-formats" role="group" aria-label="Export formats">
            {FORMATS.map((f) => (
              <button
                key={f.id}
                type="button"
                className="export-format-card"
                aria-pressed={selected.has(f.id)}
                onClick={() => toggle(f.id)}
              >
                <div className="export-format-name">{f.name}</div>
                <div className="export-format-desc">{f.desc}</div>
              </button>
            ))}
          </div>
        </div>

        <div className="field">
          <label className="field-label" htmlFor={stemId}>
            File name
          </label>
          <input
            id={stemId}
            className="input"
            placeholder={`voicegen-${jobId}`}
            value={stem}
            onChange={(e) => setStem(e.target.value)}
          />
          <p className="field-hint">
            Every export embeds synthetic-audio provenance metadata. This cannot be disabled.
          </p>
        </div>

        {error ? (
          <p role="alert" style={{ color: "var(--danger)" }}>
            {error}
          </p>
        ) : null}
      </div>
    </Dialog>
  );
}
