# VoiceGenAI UI

Desktop/Web UI for the VoiceGenAI voice-generation studio. Tauri v2 shell +
React 18 + TypeScript. All audio intelligence lives in the Python sidecar
(`../sidecar/presence_sidecar`); this app is a client of that API and keeps
the bearer token in memory only.

## Architecture

```
src/
  lib/
    api/          typed client (client.ts), contracts (types.ts), SSE (sse.ts),
                  error mapping (errors.ts), React Query hooks (hooks.ts)
    sidecar/      connection lifecycle (Tauri IPC / browser dev)
    state/        small session store (navigation, active voice, toasts, theme)
    fs/           reading backend-written files (exports) via Tauri fs / dev middleware
    qcView.ts     capture-QC → friendly check rows (derived, never fabricated)
  components/
    ui/           design-system primitives (Button, Dialog, Slider, …)
    layout/       AppShell (sidebar, topbar, connection pill)
    audio/        MicRecorder (PCM→WAV), AudioPlayer, Waveform
    profiles/     CreateVoiceFlow, QCPanel, DeleteVoiceDialog, VoiceSelector
    studio/       ScriptEditor, PronunciationEditor, PresetGrid, AdvancedPanel,
                  GenerateControls, GenerationProgress, SegmentReview, ExportDialog, OutputPanel
    onboarding/   first-run flow
  pages/          Studio, Voices, Library, Settings
src-tauri/        Rust shell: spawns sidecar, parses PRESENCE_SIDECAR_READY,
                  restart/crash handling, fs+http plugins (loopback only)
```

## Develop (browser)

```bash
# 1. start the sidecar (from the repo root)
../.venv/bin/presence sidecar --port 8765
#    → note the printed: PRESENCE_SIDECAR_READY token=… port=8765

# 2. start the UI
npm install
VITE_SIDECAR_TOKEN=<token> npm run dev     # or paste the token in the connect screen
```

Browser dev talks to the sidecar through the Vite same-origin proxy (the
sidecar has no CORS headers by design). `VITE_SIDECAR_PORT` changes the
proxy target (default 8765).

## Desktop (Tauri)

```bash
npm run tauri dev
```

The shell finds the sidecar in this order:
1. `VOICEGENAI_SIDECAR_CMD` env var (explicit command)
2. bundled resource `sidecar/presence-sidecar` (packaged builds)
3. repo dev venv `../.venv/bin/presence-sidecar`

The token never touches logs, storage, or the UI.

## Tests

```bash
npm run test        # vitest (unit + component behavior)
npm run typecheck   # tsc -b --noEmit
npm run build       # production bundle
```

## Security invariants

- Sidecar binds 127.0.0.1 only; the shell never re-binds it.
- No voice data, scripts, tokens, or audio leave the device.
- Provenance embedding is mandatory; the UI has no toggle for it.
- Deletion success is only reported after the backend confirms zero residual
  files.
