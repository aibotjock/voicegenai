import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GenerateControls, generationReadiness } from "./GenerateControls";
import type { VoiceProfile } from "../../lib/api/types";

const baseVoice: VoiceProfile = {
  id: "p1",
  name: "My Voice",
  status: "active",
  created_at: "2026-09-09T00:00:00Z",
  capture_kind: "guided",
};

function readyArgs(over: Partial<Parameters<typeof generationReadiness>[0]> = {}) {
  return {
    sidecarReady: true,
    voice: baseVoice,
    script: "Hello world",
    design: "podcast",
    generating: false,
    ...over,
  };
}

describe("generationReadiness", () => {
  it("is ready with voice + script + style", () => {
    expect(generationReadiness(readyArgs())).toEqual({ ready: true, reason: null });
  });

  it("blocks offline sidecar first", () => {
    const r = generationReadiness(readyArgs({ sidecarReady: false, voice: null, script: "" }));
    expect(r.ready).toBe(false);
    expect(r.reason).toMatch(/offline/i);
  });

  it("blocks with no voice", () => {
    expect(generationReadiness(readyArgs({ voice: null })).reason).toBe("Select a voice");
  });

  it("blocks empty script", () => {
    expect(generationReadiness(readyArgs({ script: "   " })).reason).toBe("Enter a script");
  });

  it("blocks missing style", () => {
    expect(generationReadiness(readyArgs({ design: null })).reason).toBe("Choose a style");
  });

  it("blocks while generating", () => {
    expect(generationReadiness(readyArgs({ generating: true })).reason).toMatch(/already running/i);
  });
});

describe("GenerateControls", () => {
  it("shows the reason when disabled", () => {
    render(
      <GenerateControls
        readiness={{ ready: false, reason: "Enter a script" }}
        generating={false}
        onGenerate={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: /generate voice/i })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("Enter a script");
  });

  it("fires onGenerate when ready", async () => {
    const onGenerate = vi.fn();
    render(
      <GenerateControls
        readiness={{ ready: true, reason: null }}
        generating={false}
        onGenerate={onGenerate}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /generate voice/i }));
    expect(onGenerate).toHaveBeenCalledOnce();
  });
});
