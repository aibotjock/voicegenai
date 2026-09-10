/**
 * Test harness: renders components with the same providers as the app and a
 * mock-fetch-backed sidecar connection. Routes requests by method+path.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { AppProvider } from "../lib/state/AppContext";
import { connection } from "../lib/sidecar/connection";
import { SidecarError } from "../lib/api/errors";

export type MockRoute = {
  method?: string;
  match: RegExp | string;
  status?: number;
  body?: unknown;
  /** When set, called with (url, init) and may return a Response. */
  handler?: (url: string, init?: RequestInit) => Promise<Response> | Response;
};

export function mockFetchWith(routes: MockRoute[]): typeof fetch {
  return (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    for (const r of routes) {
      const pathMatch =
        typeof r.match === "string" ? url.includes(r.match) : r.match.test(url);
      const methodMatch = !r.method || r.method.toUpperCase() === method;
      if (pathMatch && methodMatch) {
        if (r.handler) return r.handler(url, init);
        return new Response(JSON.stringify(r.body ?? {}), {
          status: r.status ?? 200,
          headers: { "Content-Type": "application/json" },
        });
      }
    }
    throw new SidecarError(null, `no mock route for ${method} ${url}`);
  }) as typeof fetch;
}

/** Point the singleton connection manager at the mock transport. */
export async function connectMock(routes: MockRoute[]): Promise<void> {
  // /health must succeed for connect() to flip to ready
  const withHealth: MockRoute[] = [
    { match: "/health", body: { status: "ok", presets: [], engines: [] } },
    ...routes,
  ];
  const ok = await connection.connect(
    { baseUrl: "http://test", token: "test-token" },
    mockFetchWith(withHealth),
  );
  if (!ok) throw new Error("mock connection failed");
}

export function renderWithProviders(ui: ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={qc}>
        <AppProvider>{children}</AppProvider>
      </QueryClientProvider>
    );
  }
  return render(ui, { wrapper: Wrapper });
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export function sseResponse(events: string): Response {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(events));
      controller.close();
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}
