/// <reference types="vitest/config" />
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { createReadStream, existsSync, readdirSync, statSync } from "node:fs";
import { extname, join, resolve } from "node:path";

// Dev-mode sidecar target. The sidecar binds 127.0.0.1 only and has no CORS
// headers, so browser development talks to it through this same-origin proxy.
const sidecarPort = process.env.VITE_SIDECAR_PORT ?? "8765";
const sidecarTarget = `http://127.0.0.1:${sidecarPort}`;

const AUDIO_TYPES: Record<string, string> = {
  ".wav": "audio/wav",
  ".mp3": "audio/mpeg",
  ".m4a": "audio/mp4",
  ".flac": "audio/flac",
  ".ogg": "audio/ogg",
};

/**
 * Dev-only middleware that lets the browser build read files the *backend*
 * already wrote to this machine (exports directory, exported masters). This
 * exists because the sidecar intentionally has no file-download route; in the
 * packaged desktop app the same capability is provided by tauri-plugin-fs.
 * Never shipped: it only exists on the Vite dev server (127.0.0.1).
 */
function devLocalFiles(): Plugin {
  return {
    name: "voicegenai-dev-local-files",
    configureServer(server) {
      server.middlewares.use("/__local-file", (req, res) => {
        const url = new URL(req.url ?? "", "http://localhost");
        const p = url.searchParams.get("path") ?? "";
        if (!p || !existsSync(p) || !statSync(p).isFile()) {
          res.statusCode = 404;
          res.end("not found");
          return;
        }
        res.setHeader(
          "Content-Type",
          AUDIO_TYPES[extname(p).toLowerCase()] ?? "application/octet-stream",
        );
        res.setHeader("Content-Length", statSync(p).size);
        createReadStream(p).pipe(res);
      });
      server.middlewares.use("/__exports", (req, res) => {
        const url = new URL(req.url ?? "", "http://localhost");
        const dir = url.searchParams.get("dir") ?? "";
        if (!dir || !existsSync(dir)) {
          res.statusCode = 404;
          res.end("[]");
          return;
        }
        const items = readdirSync(dir)
          .filter((f) => statSync(join(dir, f)).isFile())
          .map((f) => {
            const st = statSync(join(dir, f));
            return {
              name: f,
              path: resolve(join(dir, f)),
              size: st.size,
              modified: st.mtime.toISOString(),
            };
          })
          .sort((a, b) => b.modified.localeCompare(a.modified));
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify(items));
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), devLocalFiles()],
  clearScreen: false,
  server: {
    // Tauri expects this exact dev port.
    port: 1420,
    strictPort: true,
    proxy: {
      "/api": { target: sidecarTarget, changeOrigin: true },
      "/health": { target: sidecarTarget, changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
