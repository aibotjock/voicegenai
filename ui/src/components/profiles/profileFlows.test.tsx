import { describe, expect, it, vi } from "vitest";
import { renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { act } from "react";
import { useGenerationJob } from "../../lib/api/hooks";
import { DeleteVoiceDialog } from "./DeleteVoiceDialog";
import type { VoiceProfile } from "../../lib/api/types";
import {
  connectMock,
  renderWithProviders,
  sseResponse,
} from "../../test/render";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppProvider } from "../../lib/state/AppContext";
import type { ReactNode } from "react";

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <AppProvider>{children}</AppProvider>
    </QueryClientProvider>
  );
}

describe("useGenerationJob (SSE-driven)", () => {
  it("applies snapshot + live events through completion", async () => {
    await connectMock([
      {
        match: /\/api\/v1\/jobs\/j1\/events/,
        handler: () =>
          sseResponse(
            "event: open\n\n" +
              'event: job\ndata: {"event":"prepared","segments":2}\n\n' +
              'event: segment\ndata: {"event":"segment","index":0,"status":"done","wer":0.01,"retries":0}\n\n' +
              'event: segment\ndata: {"event":"segment","index":1,"status":"flagged","wer":0.3,"retries":3}\n\n' +
              'event: job\ndata: {"event":"done","result":{"segments":2,"flagged":1}}\n\n',
          ),
      },
      {
        match: /\/api\/v1\/jobs\/j1$/,
        body: {
          id: "j1",
          status: "running",
          created_at: "2026-09-09T00:00:00Z",
          segments: [
            { index: 0, text: "A", spoken_text: "A", status: "synthesizing", wer: null, retries: 0, wav_path: "", error: "" },
            { index: 1, text: "B", spoken_text: "B", status: "pending", wer: null, retries: 0, wav_path: "", error: "" },
          ],
          error: "",
          result: {},
        },
      },
    ]);

    const { result } = renderHook(() => useGenerationJob("j1"), { wrapper });

    await waitFor(() => expect(result.current?.segments).toHaveLength(2));
    await waitFor(() => expect(result.current?.status).toBe("done"));
    expect(result.current?.segments[0].status).toBe("done");
    expect(result.current?.segments[1].status).toBe("flagged");
    expect(result.current?.segments[1].retries).toBe(3);
    expect(result.current?.result).toMatchObject({ segments: 2, flagged: 1 });
  });
});

describe("DeleteVoiceDialog", () => {
  const profile: VoiceProfile = {
    id: "p1",
    name: "My Voice",
    status: "active",
    created_at: "2026-09-09T00:00:00Z",
    capture_kind: "guided",
  };

  it("requires explicit confirmation and reports success only after backend confirms", async () => {
    await connectMock([
      {
        method: "DELETE",
        match: /\/api\/v1\/profiles\/p1/,
        body: { ok: true, deleted: 4, residual: 0 },
      },
    ]);
    const onDeleted = vi.fn();
    renderWithProviders(
      <DeleteVoiceDialog profile={profile} open onClose={() => {}} onDeleted={onDeleted} />,
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Delete Voice" }));
    await waitFor(() => expect(onDeleted).toHaveBeenCalledOnce());
  });

  it("shows an honest error when the backend reports residual files", async () => {
    await connectMock([
      {
        method: "DELETE",
        match: /\/api\/v1\/profiles\/p1/,
        status: 400,
        body: { detail: "delete failed — residual files remain" },
      },
    ]);
    const onDeleted = vi.fn();
    renderWithProviders(
      <DeleteVoiceDialog profile={profile} open onClose={() => {}} onDeleted={onDeleted} />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Delete Voice" }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/not be fully deleted/i),
    );
    expect(onDeleted).not.toHaveBeenCalled();
  });
});

// silence act() warnings from async state updates in these integration tests
void act;
