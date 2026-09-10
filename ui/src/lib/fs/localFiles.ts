/**
 * Reading local files the backend wrote (exports live on this machine).
 *
 * Desktop: tauri-plugin-fs (scope-limited to the app's data directories).
 * Browser dev: the Vite dev middleware (/__local-file, /__exports).
 *
 * The sidecar intentionally has no file-download route; the shell layer
 * provides this instead.
 */
import { isTauri } from "../sidecar/connection";
import type { ExportFile } from "../api/types";

const AUDIO_EXT = new Set([".wav", ".mp3", ".m4a", ".flac", ".ogg"]);
const META_EXT = new Set([".json", ".txt"]);

function ext(name: string): string {
  const i = name.lastIndexOf(".");
  return i >= 0 ? name.slice(i).toLowerCase() : "";
}

/** Read a local file as a Blob (desktop: plugin-fs; dev: middleware). */
export async function readLocalFileBlob(path: string): Promise<Blob> {
  if (isTauri()) {
    const { readFile } = await import("@tauri-apps/plugin-fs");
    const bytes = await readFile(path);
    const mime =
      ext(path) === ".mp3"
        ? "audio/mpeg"
        : ext(path) === ".m4a"
          ? "audio/mp4"
          : "audio/wav";
    return new Blob([bytes], { type: mime });
  }
  const res = await fetch(`/__local-file?path=${encodeURIComponent(path)}`);
  if (!res.ok) throw new Error(`could not read local file (${res.status})`);
  return res.blob();
}

/** Load a local audio file into a blob URL suitable for <audio src>. */
export async function localFileToObjectUrl(path: string): Promise<string> {
  return URL.createObjectURL(await readLocalFileBlob(path));
}

/** List files in the backend's exports directory (audio + sidecar metadata). */
export async function listExportFiles(dir: string): Promise<ExportFile[]> {
  if (!dir) return [];
  if (isTauri()) {
    const { readDir } = await import("@tauri-apps/plugin-fs");
    const entries = await readDir(dir);
    return entries
      .filter((e) => e.isFile)
      .filter((e) => AUDIO_EXT.has(ext(e.name)) || META_EXT.has(ext(e.name)))
      .map((e) => ({
        name: e.name,
        path: `${dir.replace(/\/$/, "")}/${e.name}`,
        size: 0, // size requires extra stat calls; filled lazily if needed
        modified: "",
      }))
      .sort((a, b) => b.name.localeCompare(a.name));
  }
  const res = await fetch(`/__exports?dir=${encodeURIComponent(dir)}`);
  if (!res.ok) return [];
  return (await res.json()) as ExportFile[];
}

/** Parse the diagnostics bundle to find the app data home (config.home). */
export function dataHomeFromDiagnostics(bundleJson: string): string | null {
  try {
    const parsed = JSON.parse(bundleJson) as { config?: { home?: string } };
    return parsed.config?.home ?? null;
  } catch {
    return null;
  }
}
