/**
 * Presentation mapping for capture QC results.
 *
 * The backend already returns plain-language issues and hard numbers; this
 * module turns the same fields into labeled check rows. Labels are pure
 * functions of backend state — quality is never fabricated.
 */
import type { QCResult } from "./api/types";
import { formatDuration } from "./format";

export const QC_MIN_DURATION_S = 30;
export const QC_MAX_DURATION_S = 600;
export const QC_MIN_SNR_DB = 12;
export const QC_MAX_SILENCE_RATIO = 0.7;

export type QcCheckId = "duration" | "noise" | "clipping" | "silence" | "speakers";

export interface QcCheckView {
  id: QcCheckId;
  label: string;
  passed: boolean;
  /** Friendly one-line state, e.g. "0:42 recorded (0:30 minimum)". */
  detail: string;
}

export type QcVerdict = "excellent" | "good" | "needs-improvement";

export function qcChecks(qc: QCResult): QcCheckView[] {
  const durationOk =
    qc.duration_s >= QC_MIN_DURATION_S && qc.duration_s <= QC_MAX_DURATION_S;
  const noiseOk = qc.snr_db >= QC_MIN_SNR_DB;
  const clipOk = qc.clipping_events === 0;
  const silenceOk = qc.silence_ratio <= QC_MAX_SILENCE_RATIO;
  const speakersOk = !qc.multi_speaker_suspect;

  return [
    {
      id: "duration",
      label: "Recording length",
      passed: durationOk,
      detail: durationOk
        ? `${formatDuration(qc.duration_s)} recorded`
        : `${formatDuration(qc.duration_s)} recorded — aim for at least ${formatDuration(QC_MIN_DURATION_S)}`,
    },
    {
      id: "noise",
      label: "Background noise",
      passed: noiseOk,
      detail: noiseOk
        ? "Background noise is low"
        : "Too much background noise — move closer to the mic or find a quieter room",
    },
    {
      id: "clipping",
      label: "Volume level",
      passed: clipOk,
      detail: clipOk
        ? "No distortion from loud volume"
        : "Some parts are too loud and distorted — lower the input level",
    },
    {
      id: "silence",
      label: "Steady speech",
      passed: silenceOk,
      detail: silenceOk
        ? "You spoke consistently"
        : "Long silent stretches — try to keep talking",
    },
    {
      id: "speakers",
      label: "Single voice",
      passed: speakersOk,
      detail: speakersOk
        ? "Only one voice detected"
        : "It sounds like more than one person — we can only use your own voice",
    },
  ];
}

export function qcVerdict(qc: QCResult): QcVerdict {
  if (!qc.ok) return "needs-improvement";
  const strong =
    qc.snr_db >= 24 &&
    qc.clipping_events === 0 &&
    qc.silence_ratio <= 0.5 &&
    qc.duration_s >= 45;
  return strong ? "excellent" : "good";
}

export const QC_VERDICT_LABEL: Record<QcVerdict, string> = {
  excellent: "Excellent",
  good: "Good",
  "needs-improvement": "Needs improvement",
};
