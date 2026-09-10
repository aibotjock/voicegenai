import { describe, expect, it } from "vitest";
import { qcChecks, qcVerdict } from "./qcView";
import type { QCResult } from "./api/types";

const base: QCResult = {
  duration_s: 45,
  sample_rate: 48000,
  snr_db: 30,
  clipping_events: 0,
  max_abs: 0.8,
  silence_ratio: 0.2,
  multi_speaker_suspect: false,
  ok: true,
  issues: [],
};

describe("qcView", () => {
  it("marks a strong clean capture as excellent", () => {
    expect(qcVerdict(base)).toBe("excellent");
  });

  it("marks an acceptable capture as good", () => {
    expect(qcVerdict({ ...base, snr_db: 14 })).toBe("good");
  });

  it("marks a refused capture as needs-improvement", () => {
    expect(qcVerdict({ ...base, ok: false, snr_db: 6 })).toBe("needs-improvement");
  });

  it("derives each check row from backend fields", () => {
    const rows = qcChecks({
      ...base,
      ok: false,
      duration_s: 8,
      snr_db: 5,
      clipping_events: 12,
      silence_ratio: 0.9,
      multi_speaker_suspect: true,
    });
    const byId = Object.fromEntries(rows.map((r) => [r.id, r]));
    expect(byId.duration.passed).toBe(false);
    expect(byId.noise.passed).toBe(false);
    expect(byId.clipping.passed).toBe(false);
    expect(byId.silence.passed).toBe(false);
    expect(byId.speakers.passed).toBe(false);
    // friendly, non-numeric guidance
    expect(byId.noise.detail).not.toMatch(/dB/);
  });

  it("passes all rows for a clean capture", () => {
    const rows = qcChecks(base);
    expect(rows.every((r) => r.passed)).toBe(true);
  });
});
