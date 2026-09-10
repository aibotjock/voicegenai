import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { GenerationProgress, describeStage } from "./GenerationProgress";
import { SegmentReview } from "./SegmentReview";
import { sanitizeStem } from "./ExportDialog";
import type { GenerationJob, GenerationSegment } from "../../lib/api/types";

function seg(over: Partial<GenerationSegment> = {}): GenerationSegment {
  return {
    index: 0,
    text: "Hello world",
    spoken_text: "Hello world",
    status: "done",
    wer: 0.02,
    retries: 0,
    wav_path: "/tmp/seg.wav",
    error: "",
    ...over,
  };
}

function job(over: Partial<GenerationJob> = {}): GenerationJob {
  return {
    id: "j1",
    status: "running",
    created_at: "2026-09-09T00:00:00Z",
    segments: [],
    error: "",
    result: {},
    ...over,
  };
}

describe("GenerationProgress stages", () => {
  it("reports preparing before segments exist", () => {
    expect(describeStage(job())).toBe("Preparing script");
  });

  it("reports the active section while synthesizing", () => {
    const j = job({ segments: [seg({ status: "synthesizing", index: 1 })] });
    expect(describeStage(j)).toBe("Generating section 2 of 1");
  });

  it("reports accuracy checks and retries distinctly", () => {
    const j = job({ segments: [seg({ status: "checking", index: 2, retries: 1 })] });
    expect(describeStage(j)).toBe("Retrying section 3 of 1");
  });

  it("reports done as Ready", () => {
    render(<GenerationProgress job={job({ status: "done" })} />);
    expect(screen.getByText("Ready")).toBeInTheDocument();
  });

  it("surfaces failure text", () => {
    render(<GenerationProgress job={job({ status: "failed", error: "engine exploded" })} />);
    expect(screen.getByRole("alert")).toHaveTextContent("engine exploded");
  });
});

describe("SegmentReview", () => {
  it("summarizes clean completion without scaring the user", () => {
    const j = job({ status: "done", segments: [seg({ index: 0 }), seg({ index: 1 })] });
    render(<SegmentReview job={j} />);
    expect(screen.getByText(/2 sections generated successfully/)).toBeInTheDocument();
    expect(screen.getByText("All sections passed")).toBeInTheDocument();
  });

  it("lists flagged sections with retry counts and keeps WER behind details", () => {
    const j = job({
      status: "done",
      segments: [
        seg({ index: 0 }),
        seg({ index: 1, status: "flagged", wer: 0.31, retries: 3, text: "Qwen is hard" }),
      ],
    });
    render(<SegmentReview job={j} />);
    expect(screen.getByText(/2 sections generated\. 1 needs review\./)).toBeInTheDocument();
    expect(screen.getByText("Section 2")).toBeInTheDocument();
    expect(screen.getByText(/Qwen is hard/)).toBeInTheDocument();
    expect(screen.getByText(/3 times/)).toBeInTheDocument();
    // WER number is present but only inside the collapsed technical details
    expect(screen.queryByText(/wer: 0.31/)).not.toBeInTheDocument();
  });

  it("renders nothing while job is mid-flight with no flags", () => {
    const { container } = render(
      <SegmentReview job={job({ status: "running", segments: [seg({ status: "synthesizing" })] })} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe("sanitizeStem", () => {
  it("keeps words, dashes and underscores; strips path-ish characters", () => {
    expect(sanitizeStem("My Take 01")).toBe("My-Take-01");
    expect(sanitizeStem("../../etc/passwd")).toBe("etcpasswd");
    expect(sanitizeStem("  spaced   out  ")).toBe("spaced-out");
  });

  it("caps length", () => {
    expect(sanitizeStem("x".repeat(200)).length).toBeLessThanOrEqual(80);
  });
});
