import { describe, expect, it, vi } from "vitest";
import { parseSseBuffer, subscribeSse } from "./sse";
import { sseResponse } from "../../test/render";

describe("parseSseBuffer", () => {
  it("parses complete events and keeps partial tail", () => {
    const { messages, rest } = parseSseBuffer(
      'event: job\ndata: {"event":"prepared","segments":3}\n\nevent: segment\ndata: {"event"',
    );
    expect(messages).toHaveLength(1);
    expect(messages[0].event).toBe("job");
    expect(JSON.parse(messages[0].data)).toEqual({ event: "prepared", segments: 3 });
    expect(rest).toContain("event: segment");
  });

  it("ignores keepalive comments and open events without data", () => {
    const { messages } = parseSseBuffer(": keepalive\n\nevent: open\n\nevent: segment\ndata: {}\n\n");
    // open has no data but a named event — passed through; comments dropped
    expect(messages.map((m) => m.event)).toEqual(["open", "segment"]);
  });

  it("handles \\r\\n line endings", () => {
    const { messages } = parseSseBuffer("event: job\r\ndata: {\"a\":1}\r\n\r\n");
    expect(messages).toHaveLength(1);
  });
});

describe("subscribeSse", () => {
  it("delivers parsed events and supports close()", async () => {
    const seen: Array<{ event: string; data: unknown }> = [];
    const fetchImpl = (async () =>
      sseResponse(
        "event: open\n\n" +
          'event: job\ndata: {"event":"prepared","segments":2}\n\n' +
          ": keepalive\n\n" +
          'event: segment\ndata: {"event":"segment","index":0,"status":"done"}\n\n' +
          'event: job\ndata: {"event":"done","result":{"segments":2}}\n\n',
      )) as unknown as typeof fetch;

    const sub = subscribeSse(
      fetchImpl,
      "http://test/events",
      { Authorization: "Bearer t" },
      (msg) => seen.push({ event: msg.event, data: msg.data ? JSON.parse(msg.data) : null }),
    );

    await vi.waitFor(() => {
      expect(seen.length).toBe(4);
    });
    expect(seen[0]).toEqual({ event: "open", data: null });
    expect(seen[1].data).toEqual({ event: "prepared", segments: 2 });
    expect(seen[2].data).toEqual({ event: "segment", index: 0, status: "done" });
    expect(seen[3].data).toEqual({ event: "done", result: { segments: 2 } });
    sub.close();
  });

  it("calls onError on transport failure", async () => {
    const onError = vi.fn();
    const fetchImpl = (async () => {
      throw new TypeError("down");
    }) as typeof fetch;
    subscribeSse(fetchImpl, "http://test/x", {}, () => {}, onError);
    await vi.waitFor(() => expect(onError).toHaveBeenCalled());
  });
});
