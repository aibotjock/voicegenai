/**
 * Sidecar errors mapped to user-facing language.
 * Raw backend exceptions are never the primary UI message; the technical
 * detail stays available for the Details expander.
 */

export class SidecarError extends Error {
  readonly status: number | null;
  readonly detail: string;

  constructor(status: number | null, detail: string) {
    super(detail);
    this.name = "SidecarError";
    this.status = status;
    this.detail = detail;
  }

  get isOffline(): boolean {
    return this.status === null;
  }
}

/** Known backend messages → friendly explanations (details stay available). */
const FRIENDLY: Array<[RegExp, string]> = [
  [/profile not found/i, "That voice no longer exists. Choose another voice."],
  [/no reference capture/i, "This voice has no reference recording. Create it again."],
  [/script produced no segments/i, "The script is empty after processing. Add some text."],
  [/unknown preset/i, "That voice style is not available. Choose another style."],
  [/unknown engine/i, "That voice engine is not available. Choose another engine."],
  [/job is not complete/i, "Generation has not finished yet."],
  [/job not found/i, "That generation is no longer available."],
  [/delete failed/i, "The voice could not be fully deleted."],
  [/invalid sidecar token/i, "The connection to the voice engine expired. Restart the app."],
];

/** Map any thrown error to a short, plain-English explanation. */
export function friendlyError(err: unknown, context?: string): string {
  if (err instanceof SidecarError) {
    if (err.isOffline) {
      return "Voice Engine is offline. Try restarting it from the status indicator.";
    }
    for (const [re, msg] of FRIENDLY) {
      if (re.test(err.detail)) return msg;
    }
    if (err.status === 401) {
      return "The connection to the voice engine expired. Restart the app.";
    }
  }
  if (context) return context;
  return "Something went wrong. Details are available below.";
}
