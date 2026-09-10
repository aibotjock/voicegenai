import { useRef, useState } from "react";
import { CheckCircle2, Upload } from "lucide-react";
import { friendlyError } from "../../lib/api/errors";
import type { QCResult } from "../../lib/api/types";
import { useCreateProfile } from "../../lib/api/hooks";
import { formatDuration } from "../../lib/format";
import { useApp } from "../../lib/state/AppContext";
import { QC_MIN_DURATION_S } from "../../lib/qcView";
import { MicRecorder } from "../audio/MicRecorder";
import type { RecordedTake } from "../audio/useMicRecorder";
import { Button } from "../ui/Button";
import { Input } from "../ui/Field";
import { QCPanel } from "./QCPanel";
import "./profiles.css";

type Step = "name" | "capture" | "result";

interface CreateVoiceFlowProps {
  /** Called with the new profile id + name after a capture passes QC. */
  onComplete: (profileId: string, name: string) => void;
  onCancel?: () => void;
  compact?: boolean;
}

/**
 * Guided voice creation: name → record or upload → recording check.
 * The backend QC is the gate; failed captures show plain-language feedback
 * and can simply be retried.
 */
export function CreateVoiceFlow({ onComplete, onCancel }: CreateVoiceFlowProps) {
  const { toast } = useApp();
  const createProfile = useCreateProfile();

  const [step, setStep] = useState<Step>("name");
  const [name, setName] = useState("");
  const [mode, setMode] = useState<"record" | "upload">("record");
  const [submitting, setSubmitting] = useState(false);
  const [qc, setQc] = useState<QCResult | null>(null);
  const [qcPassed, setQcPassed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  const submit = async (audio: Blob, captureKind: "guided" | "upload", filename: string) => {
    setSubmitting(true);
    setError(null);
    try {
      const result = await createProfile.mutateAsync({
        name: name.trim(),
        captureKind,
        audio,
        filename,
      });
      setQc(result.qc);
      setQcPassed(result.ok);
      setStep("result");
      if (!result.ok) {
        toast("info", "Recording needs improvement — see the feedback below.");
      }
    } catch (err) {
      setError(friendlyError(err, "Could not create the voice profile."));
    } finally {
      setSubmitting(false);
    }
  };

  const submitTake = (take: RecordedTake) => void submit(take.blob, "guided", "capture.wav");

  const submitFile = (file: File) => {
    void submit(file, "upload", file.name);
  };

  const retry = () => {
    setQc(null);
    setQcPassed(false);
    setStep("capture");
  };

  return (
    <div className="create-flow">
      <ol className="create-steps" aria-label="Voice creation steps">
        <StepItem label="Name" active={step === "name"} done={step !== "name"} />
        <StepItem label="Record or upload" active={step === "capture"} done={step === "result"} />
        <StepItem label="Recording check" active={step === "result"} done={qcPassed} />
      </ol>

      {step === "name" && (
        <>
          <Input
            label="Voice name"
            placeholder='e.g. "My Voice"'
            value={name}
            onChange={(e) => setName(e.target.value)}
            hint="This name is only stored on this device."
            autoFocus
          />
          <div style={{ display: "flex", gap: 8 }}>
            {onCancel ? (
              <Button variant="ghost" onClick={onCancel}>
                Cancel
              </Button>
            ) : null}
            <Button
              variant="primary"
              disabled={!name.trim()}
              onClick={() => setStep("capture")}
            >
              Continue
            </Button>
          </div>
        </>
      )}

      {step === "capture" && (
        <>
          <div className="capture-tabs" role="group" aria-label="Capture method">
            <button
              type="button"
              className="capture-tab"
              aria-pressed={mode === "record"}
              onClick={() => setMode("record")}
            >
              Record microphone
            </button>
            <button
              type="button"
              className="capture-tab"
              aria-pressed={mode === "upload"}
              onClick={() => setMode("upload")}
            >
              Upload audio
            </button>
          </div>

          {mode === "record" ? (
            <MicRecorder
              onSubmit={submitTake}
              submitting={submitting}
              recommendedSeconds={QC_MIN_DURATION_S}
            />
          ) : (
            <div
              className={dragOver ? "upload-drop upload-drop-dragover" : "upload-drop"}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                const f = e.dataTransfer.files?.[0];
                if (f) submitFile(f);
              }}
            >
              <Upload size={22} aria-hidden="true" />
              <p>
                Drop an audio file here, or{" "}
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => fileRef.current?.click()}
                >
                  browse
                </button>
              </p>
              <p className="field-hint">
                WAV, MP3, M4A or FLAC — at least {formatDuration(QC_MIN_DURATION_S)} of your voice.
              </p>
              <input
                ref={fileRef}
                type="file"
                accept="audio/*,.wav,.mp3,.m4a,.flac,.ogg"
                className="sr-only"
                aria-label="Choose audio file"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) submitFile(f);
                }}
              />
              {submitting ? <p className="field-hint">Checking recording…</p> : null}
            </div>
          )}

          {error ? <p className="recorder-error" role="alert">{error}</p> : null}

          <div>
            <Button variant="ghost" onClick={() => setStep("name")} disabled={submitting}>
              Back
            </Button>
          </div>
        </>
      )}

      {step === "result" && qc && (
        <>
          <QCPanel qc={qc} />
          {qcPassed ? (
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <CheckCircle2 size={16} style={{ color: "var(--success)" }} aria-hidden="true" />
              <span>
                <strong>{name}</strong> was created and is ready to use.
              </span>
              <Button
                variant="primary"
                onClick={() => {
                  const id = (createProfile.data as { profile_id?: string } | undefined)?.profile_id;
                  if (id) onComplete(id, name.trim());
                }}
              >
                Continue
              </Button>
            </div>
          ) : (
            <div style={{ display: "flex", gap: 8 }}>
              <Button variant="primary" onClick={retry}>
                Try again
              </Button>
              {onCancel ? (
                <Button variant="ghost" onClick={onCancel}>
                  Cancel
                </Button>
              ) : null}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function StepItem({ label, active, done }: { label: string; active?: boolean; done?: boolean }) {
  return (
    <li
      className={[
        "create-step",
        active ? "create-step-active" : "",
        done ? "create-step-done" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      aria-current={active ? "step" : undefined}
    >
      {done ? <CheckCircle2 size={14} aria-hidden="true" /> : null}
      {label}
    </li>
  );
}
