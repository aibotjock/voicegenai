import { describe, expect, it } from "vitest";
import { friendlyError, SidecarError } from "./errors";

describe("friendlyError", () => {
  it("maps offline to the connection message", () => {
    expect(friendlyError(new SidecarError(null, "network request failed"))).toMatch(/offline/i);
  });

  it("maps 401 without detail match to session-expired copy", () => {
    expect(friendlyError(new SidecarError(401, "unauthorized"))).toMatch(/expired/i);
  });

  it("falls back to context for unknown errors", () => {
    expect(friendlyError(new Error("boom"), "Export failed.")).toBe("Export failed.");
  });

  it("never exposes raw detail in the fallback", () => {
    const msg = friendlyError(new Error("TypeError: x is not a function at line 42"));
    expect(msg).not.toMatch(/TypeError/);
  });
});
