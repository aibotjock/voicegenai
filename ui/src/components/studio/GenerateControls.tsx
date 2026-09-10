import { Sparkles } from "lucide-react";
import type { VoiceProfile } from "../../lib/api/types";
import { Button } from "../ui/Button";
import { Spinner } from "../ui/Feedback";
import "./studio.css";

export interface GenerateReadiness {
  ready: boolean;
  /** Plain reason shown when the primary action is disabled. */
  reason: string | null;
}

/**
 * The central rule for when generation can start. Disabled controls always
 * explain themselves via `reason`.
 */
export function generationReadiness(args: {
  sidecarReady: boolean;
  voice: VoiceProfile | null;
  script: string;
  design: string | null;
  generating: boolean;
}): GenerateReadiness {
  if (!args.sidecarReady) return { ready: false, reason: "Voice engine is offline" };
  if (args.generating) return { ready: false, reason: "Generation is already running" };
  if (!args.voice) return { ready: false, reason: "Select a voice" };
  if (!args.script.trim()) return { ready: false, reason: "Enter a script" };
  if (!args.design) return { ready: false, reason: "Choose a style" };
  return { ready: true, reason: null };
}

interface GenerateControlsProps {
  readiness: GenerateReadiness;
  generating: boolean;
  onGenerate: () => void;
}

export function GenerateControls({ readiness, generating, onGenerate }: GenerateControlsProps) {
  return (
    <div className="generate-panel">
      <Button
        variant="primary"
        size="lg"
        disabled={!readiness.ready}
        onClick={onGenerate}
      >
        {generating ? <Spinner /> : <Sparkles size={18} aria-hidden="true" />}
        {generating ? "Generating…" : "Generate Voice"}
      </Button>
      {!readiness.ready && readiness.reason ? (
        <p className="generate-reason" role="status">
          {readiness.reason}
        </p>
      ) : null}
    </div>
  );
}
