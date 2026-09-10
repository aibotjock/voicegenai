/**
 * Minimal SSE-over-fetch parser.
 *
 * EventSource cannot set the Authorization header, so job progress is read
 * from fetch's ReadableStream instead. Handles the sidecar's format:
 *   event: <kind>\ndata: <json>\n\n   plus  ": keepalive" comments.
 */

export interface RawSseMessage {
  event: string;
  data: string;
}

/** Parse one SSE text chunk buffer, returning complete messages + rest. */
export function parseSseBuffer(buffer: string): {
  messages: RawSseMessage[];
  rest: string;
} {
  const messages: RawSseMessage[] = [];
  // Events are separated by a blank line. Work on \n-normalized text.
  const normalized = buffer.replace(/\r\n/g, "\n");
  const parts = normalized.split("\n\n");
  const rest = parts.pop() ?? "";
  for (const part of parts) {
    let event = "message";
    const dataLines: string[] = [];
    for (const line of part.split("\n")) {
      if (line.startsWith(":")) continue; // keepalive / comment
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
    }
    if (dataLines.length > 0 || event !== "message") {
      messages.push({ event, data: dataLines.join("\n") });
    }
  }
  return { messages, rest };
}

export interface SseSubscription {
  close: () => void;
}

type FetchLike = typeof fetch;

/**
 * Subscribe to an SSE endpoint via fetch. Calls `onMessage` per event and
 * `onError` on transport failure. Returns a handle with close().
 */
export function subscribeSse(
  fetchImpl: FetchLike,
  url: string,
  headers: Record<string, string>,
  onMessage: (msg: RawSseMessage) => void,
  onError?: (err: unknown) => void,
): SseSubscription {
  const controller = new AbortController();
  let closed = false;

  (async () => {
    try {
      const res = await fetchImpl(url, {
        headers: { Accept: "text/event-stream", ...headers },
        signal: controller.signal,
      });
      if (!res.ok || !res.body) {
        throw new Error(`SSE request failed (${res.status})`);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const { messages, rest } = parseSseBuffer(buffer);
        buffer = rest;
        for (const m of messages) onMessage(m);
      }
      // flush any trailing event
      if (buffer.trim().length > 0) {
        const { messages } = parseSseBuffer(buffer + "\n\n");
        for (const m of messages) onMessage(m);
      }
    } catch (err) {
      if (!closed && !(err instanceof DOMException && err.name === "AbortError")) {
        onError?.(err);
      }
    }
  })();

  return {
    close: () => {
      closed = true;
      controller.abort();
    },
  };
}
