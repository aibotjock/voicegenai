import { useEffect, useMemo, useState } from "react";
import { FileAudio, FolderOpen, Play } from "lucide-react";
import { useDiagnostics } from "../lib/api/hooks";
import type { ExportFile } from "../lib/api/types";
import { formatBytes, formatDateTime } from "../lib/format";
import { dataHomeFromDiagnostics, listExportFiles } from "../lib/fs/localFiles";
import { useApp } from "../lib/state/AppContext";
import { AudioPlayer } from "../components/audio/AudioPlayer";
import { useAudioFile } from "../components/audio/useAudioFile";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { EmptyState } from "../components/ui/Feedback";
import "./pages.css";

const AUDIO_RE = /\.(wav|mp3|m4a|flac|ogg)$/i;

/**
 * Library: what actually exists — this session's generations (in memory)
 * and the files in the backend's exports directory. No fabricated history:
 * when the app restarts, session items are gone and exports remain on disk.
 */
export function LibraryPage() {
  const { sessionGenerations } = useApp();
  const { data: diagnostics } = useDiagnostics();
  const [exportsDir, setExportsDir] = useState<string | null>(null);
  const [files, setFiles] = useState<ExportFile[] | null>(null);
  const [playPath, setPlayPath] = useState<string | null>(null);

  useEffect(() => {
    const home = diagnostics ? dataHomeFromDiagnostics(diagnostics.bundle) : null;
    if (!home) return;
    const dir = `${home.replace(/\/$/, "")}/exports`;
    setExportsDir(dir);
    listExportFiles(dir)
      .then(setFiles)
      .catch(() => setFiles([]));
  }, [diagnostics]);

  const audioFiles = useMemo(
    () => (files ?? []).filter((f) => AUDIO_RE.test(f.name)),
    [files],
  );

  return (
    <div>
      <header className="page-head">
        <div>
          <h1 className="page-title">Library</h1>
          <p className="page-sub">Generated audio and exports on this device.</p>
        </div>
      </header>

      <section className="page-section" aria-labelledby="lib-recent">
        <h2 className="page-section-title" id="lib-recent">
          Recent Session
        </h2>
        {sessionGenerations.length === 0 ? (
          <EmptyState
            icon={<FileAudio size={22} />}
            title="Nothing generated yet this session"
            body="Audio you generate in Studio appears here while the app is open."
          />
        ) : (
          sessionGenerations.map((g) => (
            <div key={g.jobId} className="lib-row">
              <FileAudio size={18} aria-hidden="true" style={{ color: "var(--text-3)" }} />
              <div style={{ minWidth: 0 }}>
                <div className="lib-name">{g.exportStem ?? `voicegen-${g.jobId}`}</div>
                <div className="lib-meta">
                  {g.voiceName} · {g.designName} · {formatDateTime(g.createdAt)}
                  {g.scriptExcerpt ? ` · “${g.scriptExcerpt}…”` : ""}
                </div>
              </div>
              {g.flagged > 0 ? (
                <Badge tone="warning" dot>
                  {g.flagged} to review
                </Badge>
              ) : (
                <Badge tone="success" dot>
                  All sections passed
                </Badge>
              )}
              {g.exportMasterPath ? (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() =>
                    setPlayPath(playPath === g.exportMasterPath ? null : g.exportMasterPath!)
                  }
                >
                  <Play size={13} aria-hidden="true" />
                  {playPath === g.exportMasterPath ? "Close" : "Play"}
                </Button>
              ) : null}
              {playPath === g.exportMasterPath && g.exportMasterPath ? (
                <div className="lib-player-wrap">
                  <InlinePlayer path={g.exportMasterPath} />
                </div>
              ) : null}
            </div>
          ))
        )}
      </section>

      <section className="page-section" aria-labelledby="lib-exports">
        <h2 className="page-section-title" id="lib-exports">
          Exports
        </h2>
        {!exportsDir ? (
          <EmptyState
            icon={<FolderOpen size={22} />}
            title="Exports location unavailable"
            body="The exports folder is reported by the voice engine once it is running."
          />
        ) : audioFiles.length === 0 ? (
          <EmptyState
            icon={<FolderOpen size={22} />}
            title="No exports yet"
            body="Exported WAV, MP3 and M4A files are stored on this device and listed here."
          />
        ) : (
          <>
            <p className="lib-meta">{exportsDir}</p>
            {audioFiles.map((f) => (
              <div key={f.path} className="lib-row">
                <FileAudio size={18} aria-hidden="true" style={{ color: "var(--text-3)" }} />
                <div style={{ minWidth: 0 }}>
                  <div className="lib-name">{f.name}</div>
                  <div className="lib-meta">
                    {f.modified ? formatDateTime(f.modified) : ""}
                    {f.size > 0 ? ` · ${formatBytes(f.size)}` : ""}
                  </div>
                </div>
                <span />
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => setPlayPath(playPath === f.path ? null : f.path)}
                >
                  <Play size={13} aria-hidden="true" />
                  {playPath === f.path ? "Close" : "Play"}
                </Button>
                {playPath === f.path ? (
                  <div className="lib-player-wrap">
                    <InlinePlayer path={f.path} />
                  </div>
                ) : null}
              </div>
            ))}
          </>
        )}
      </section>
    </div>
  );
}

function InlinePlayer({ path }: { path: string }) {
  const audio = useAudioFile(path);
  if (audio.status === "ready" && audio.audio) {
    return (
      <AudioPlayer
        src={audio.audio.url}
        peaks={audio.audio.peaks}
        durationS={audio.audio.durationS}
      />
    );
  }
  if (audio.status === "error") {
    return <p className="lib-meta">Could not load this file for playback.</p>;
  }
  return <p className="lib-meta">Loading…</p>;
}
