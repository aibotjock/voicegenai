/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Dev-only: pre-seed the sidecar token (kept in memory, never stored). */
  readonly VITE_SIDECAR_TOKEN?: string;
  readonly VITE_SIDECAR_PORT?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
