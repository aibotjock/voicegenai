import { describe, expect, it } from "vitest";
import { SidecarClient } from "./client";
import { SidecarError } from "./errors";
import { mockFetchWith } from "../../test/render";

const conn = { baseUrl: "http://test", token: "secret-token" };

describe("SidecarClient", () => {
  it("health() does not send the bearer token", async () => {
    let seenAuth: string | null = null;
    const fetchImpl = (async (_input: RequestInfo | URL, init?: RequestInit) => {
      seenAuth = (init?.headers as Record<string, string>)?.Authorization ?? null;
      return new Response(JSON.stringify({ status: "ok" }), { status: 200 });
    }) as typeof fetch;
    const client = new SidecarClient(conn, fetchImpl);
    await client.health();
    expect(seenAuth).toBeNull();
  });

  it("sends the bearer token on authenticated routes", async () => {
    let seenAuth: string | null = null;
    const fetchImpl = (async (_input: RequestInfo | URL, init?: RequestInit) => {
      seenAuth = (init?.headers as Record<string, string>)?.Authorization ?? null;
      return new Response("[]", { status: 200 });
    }) as typeof fetch;
    const client = new SidecarClient(conn, fetchImpl);
    await client.profiles();
    expect(seenAuth).toBe("Bearer secret-token");
  });

  it("maps 401 to a SidecarError with backend detail", async () => {
    const client = new SidecarClient(
      conn,
      mockFetchWith([
        { match: "/api/v1/engines", status: 401, body: { detail: "invalid sidecar token" } },
      ]),
    );
    const err = await client.engines().catch((e) => e);
    expect(err).toBeInstanceOf(SidecarError);
    expect(err.status).toBe(401);
    expect(err.detail).toBe("invalid sidecar token");
  });

  it("maps network failure to an offline SidecarError", async () => {
    const fetchImpl = (async () => {
      throw new TypeError("fetch failed");
    }) as typeof fetch;
    const client = new SidecarClient(conn, fetchImpl);
    const err = await client.profiles().catch((e) => e);
    expect(err).toBeInstanceOf(SidecarError);
    expect(err.status).toBeNull();
    expect(err.isOffline).toBe(true);
  });

  it("createProfile posts multipart form fields", async () => {
    let contentType = "";
    let form: FormData | null = null;
    const fetchImpl = (async (_input: RequestInfo | URL, init?: RequestInit) => {
      contentType = String(
        (init?.headers as Record<string, string> | undefined)?.["Content-Type"] ?? "",
      );
      form = init?.body as FormData;
      return new Response(
        JSON.stringify({ ok: true, profile_id: "abc", qc: { ok: true } }),
        { status: 200 },
      );
    }) as typeof fetch;
    const client = new SidecarClient(conn, fetchImpl);
    const res = await client.createProfile("My Voice", "guided", new Blob(["wav"]));
    expect(res.ok).toBe(true);
    // Content-Type intentionally not set manually — the browser adds the boundary.
    expect(contentType).toBe("");
    expect(form!.get("name")).toBe("My Voice");
    expect(form!.get("capture_kind")).toBe("guided");
    expect(form!.get("capture")).toBeTruthy();
  });

  it("generate posts the exact request contract", async () => {
    let payload: Record<string, unknown> = {};
    const fetchImpl = (async (_input: RequestInfo | URL, init?: RequestInit) => {
      payload = JSON.parse(String(init?.body));
      return new Response(JSON.stringify({ job_id: "j1", status: "queued" }), { status: 200 });
    }) as typeof fetch;
    const client = new SidecarClient(conn, fetchImpl);
    const res = await client.generate({
      script: "Hello world",
      profile_id: "p1",
      design: "podcast",
      seed: 42,
      check_wer: true,
      glossary: [{ term: "Qwen", say_as: "kwen" }],
    });
    expect(res.job_id).toBe("j1");
    expect(payload).toMatchObject({
      script: "Hello world",
      profile_id: "p1",
      design: "podcast",
      seed: 42,
      check_wer: true,
      glossary: [{ term: "Qwen", say_as: "kwen" }],
    });
  });

  it("exportJob posts formats + stem", async () => {
    let payload: Record<string, unknown> = {};
    const fetchImpl = (async (_input: RequestInfo | URL, init?: RequestInit) => {
      payload = JSON.parse(String(init?.body));
      return new Response(
        JSON.stringify({
          ok: true,
          master: "/x.wav",
          mp3: "/x.mp3",
          m4a: null,
          sidecar: "/x.wav.presence.json",
          loudness: { integrated_lufs: -16, true_peak_db: -1.6, lra_lu: 4 },
          provenance: { synthetic: true },
        }),
        { status: 200 },
      );
    }) as typeof fetch;
    const client = new SidecarClient(conn, fetchImpl);
    const res = await client.exportJob("j1", { formats: "wav,mp3", stem: "take-1" });
    expect(payload).toEqual({ formats: "wav,mp3", stem: "take-1" });
    expect(res.mp3).toBe("/x.mp3");
    expect(res.m4a).toBeNull();
  });

  it("deleteProfile surfaces backend 400 detail", async () => {
    const client = new SidecarClient(
      conn,
      mockFetchWith([
        {
          method: "DELETE",
          match: /\/api\/v1\/profiles\/p1$/,
          status: 400,
          body: { detail: "delete failed — residual files remain" },
        },
      ]),
    );
    const err = await client.deleteProfile("p1").catch((e) => e);
    expect(err.status).toBe(400);
    expect(err.detail).toMatch(/residual/);
  });
});
