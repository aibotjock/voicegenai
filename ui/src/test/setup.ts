import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
});

// jsdom may lack localStorage depending on environment config (and Node's
// own global localStorage can shadow it without a backing file)
function localStorageUsable(): boolean {
  try {
    window.localStorage.setItem("__probe__", "1");
    window.localStorage.removeItem("__probe__");
    return true;
  } catch {
    return false;
  }
}
if (typeof window.localStorage === "undefined" || !localStorageUsable()) {
  const store = new Map<string, string>();
  Object.defineProperty(window, "localStorage", {
    value: {
      getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
      setItem: (k: string, v: string) => void store.set(k, String(v)),
      removeItem: (k: string) => void store.delete(k),
      clear: () => store.clear(),
      get length() {
        return store.size;
      },
      key: (i: number) => [...store.keys()][i] ?? null,
    },
    configurable: true,
  });
}

// jsdom gaps used by components under test (matchMedia may exist but be
// a non-function placeholder — check callability)
if (typeof window.matchMedia !== "function") {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
}
