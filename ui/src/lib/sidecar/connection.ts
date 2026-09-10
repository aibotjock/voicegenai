/**
 * Sidecar connection resolution + lifecycle.
 *
 * Desktop (Tauri): the Rust shell spawns the sidecar, parses the
 * PRESENCE_SIDECAR_READY launch line, and hands { port, token } to the
 * webview over IPC. HTTP goes through tauri-plugin-http because the
 * sidecar deliberately sends no CORS headers.
 *
 * Browser dev: the Vite dev server proxies /api and /health to the sidecar,
 * so baseUrl is "" (same-origin). The per-launch token is entered once in
 * the connect screen and held in memory only — never in web storage.
 */
import { SidecarClient, type SidecarConnectionInfo } from "../api/client";

export type SidecarStatus = "connecting" | "ready" | "offline" | "needs-credentials";

export interface SidecarSnapshot {
  status: SidecarStatus;
  /** OS port, when known (desktop mode). Never includes the token. */
  port: number | null;
  detail?: string;
}

type Listener = (s: SidecarSnapshot) => void;

export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

/** Holds the active client; token lives here and nowhere else. */
class SidecarConnectionManager {
  private client: SidecarClient | null = null;
  private snapshot: SidecarSnapshot = { status: "connecting", port: null };
  private listeners = new Set<Listener>();

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn);
    fn(this.snapshot);
    return () => this.listeners.delete(fn);
  }

  getSnapshot(): SidecarSnapshot {
    return this.snapshot;
  }

  getClient(): SidecarClient | null {
    return this.client;
  }

  private emit(s: SidecarSnapshot) {
    this.snapshot = s;
    for (const fn of this.listeners) fn(s);
  }

  /** Establish a connection from explicit info (used by both modes). */
  async connect(info: SidecarConnectionInfo, fetchImpl?: typeof fetch): Promise<boolean> {
    const client = new SidecarClient(info, fetchImpl);
    try {
      await client.health();
      this.client = client;
      const port = portFromBaseUrl(info.baseUrl);
      this.emit({ status: "ready", port });
      return true;
    } catch {
      this.client = null;
      this.emit({ status: "offline", port: null });
      return false;
    }
  }

  markOffline(detail?: string) {
    this.emit({ status: "offline", port: this.snapshot.port, detail });
  }

  /** Periodic health revalidation with the already-connected client. */
  async revalidate(): Promise<void> {
    if (!this.client) return;
    try {
      await this.client.health();
      if (this.snapshot.status !== "ready") {
        this.emit({ status: "ready", port: this.snapshot.port });
      }
    } catch {
      if (this.snapshot.status === "ready") this.markOffline("health check failed");
    }
  }

  setNeedsCredentials() {
    this.emit({ status: "needs-credentials", port: null });
  }
}

function portFromBaseUrl(baseUrl: string): number | null {
  const m = /:(\d+)/.exec(baseUrl);
  return m ? Number(m[1]) : null;
}

export const connection = new SidecarConnectionManager();

/** Desktop: ask the Rust shell for { port, token } and connect via plugin-http. */
export async function connectViaTauri(): Promise<boolean> {
  const { invoke } = await import("@tauri-apps/api/core");
  const http = await import("@tauri-apps/plugin-http");
  const info = await invoke<{ port: number; token: string }>("sidecar_connection");
  return connection.connect(
    { baseUrl: `http://127.0.0.1:${info.port}`, token: info.token },
    http.fetch as unknown as typeof fetch,
  );
}

/** Desktop: ask the Rust shell to restart a crashed sidecar. */
export async function restartViaTauri(): Promise<boolean> {
  const { invoke } = await import("@tauri-apps/api/core");
  await invoke("restart_sidecar");
  return connectViaTauri();
}

/** Browser dev: token entered in the connect screen; proxy provides origin. */
export async function connectViaDevToken(token: string): Promise<boolean> {
  return connection.connect({ baseUrl: "", token });
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

/**
 * Desktop: subscribe to sidecar lifecycle events so a crash or restart is
 * reflected in the UI without polling.
 */
export async function listenSidecarEvents(): Promise<() => void> {
  if (!isTauri()) return () => undefined;
  const { listen } = await import("@tauri-apps/api/event");
  const un1 = await listen("sidecar://ready", () => {
    if (connection.getSnapshot().status !== "ready") {
      void connectViaTauri().catch(() => connection.markOffline());
    }
  });
  const un2 = await listen("sidecar://exit", () => {
    connection.markOffline("sidecar exited");
  });
  const un3 = await listen("sidecar://start-failed", () => {
    connection.markOffline("sidecar failed to start");
  });
  return () => {
    un1();
    un2();
    un3();
  };
}

/**
 * Boot the connection for the current environment.
 * Returns the initial status the UI should render.
 */
export async function bootstrapConnection(): Promise<void> {
  if (isTauri()) {
    // The Rust shell spawns the sidecar asynchronously; wait for the
    // handshake while the UI shows "Starting Voice Engine…".
    for (let attempt = 0; attempt < 40; attempt += 1) {
      const ok = await connectViaTauri().catch(() => false);
      if (ok) return;
      await sleep(500);
    }
    connection.markOffline("sidecar did not answer");
    return;
  }
  // Browser dev: try an env-provided token first (VITE_SIDECAR_TOKEN),
  // otherwise ask the user via the connect screen.
  const envToken = import.meta.env.VITE_SIDECAR_TOKEN as string | undefined;
  if (envToken) {
    const ok = await connectViaDevToken(envToken);
    if (!ok) connection.setNeedsCredentials();
  } else {
    connection.setNeedsCredentials();
  }
}
