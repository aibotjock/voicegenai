import { useState } from "react";
import { Mic, Plus, Trash2 } from "lucide-react";
import { useProfiles } from "../lib/api/hooks";
import type { VoiceProfile } from "../lib/api/types";
import { formatDateTime } from "../lib/format";
import { useApp } from "../lib/state/AppContext";
import { CreateVoiceFlow } from "../components/profiles/CreateVoiceFlow";
import { DeleteVoiceDialog } from "../components/profiles/DeleteVoiceDialog";
import { Button } from "../components/ui/Button";
import { Dialog } from "../components/ui/Dialog";
import { EmptyState, Spinner } from "../components/ui/Feedback";
import "../components/profiles/profiles.css";

/**
 * Voices: all profiles with actions.
 * No rename control — the backend has no rename route.
 */
export function VoicesPage() {
  const { data: profiles, isLoading } = useProfiles();
  const { setPage, setActiveVoiceId } = useApp();
  const [createOpen, setCreateOpen] = useState(false);
  const [deleteFor, setDeleteFor] = useState<VoiceProfile | null>(null);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <h1 style={{ fontSize: "var(--text-2xl)", fontWeight: 700 }}>Voices</h1>
          <p style={{ color: "var(--text-2)" }}>
            Your cloned voices. Stored encrypted on this device only.
          </p>
        </div>
        <Button variant="primary" onClick={() => setCreateOpen(true)}>
          <Plus size={15} aria-hidden="true" /> Add Voice
        </Button>
      </header>

      {isLoading ? (
        <Spinner large />
      ) : !profiles || profiles.length === 0 ? (
        <EmptyState
          icon={<Mic size={22} />}
          title="No voices yet"
          body="Create your first voice by recording yourself. The recording never leaves this device."
          action={
            <Button variant="primary" onClick={() => setCreateOpen(true)}>
              <Plus size={15} aria-hidden="true" /> Create Voice
            </Button>
          }
        />
      ) : (
        <div className="voice-grid">
          {profiles.map((p) => (
            <article key={p.id} className="voice-card">
              <div className="voice-card-head">
                <div>
                  <h2 className="voice-name">{p.name}</h2>
                  <p className="voice-meta">
                    Created {formatDateTime(p.created_at)} ·{" "}
                    {p.capture_kind === "upload" ? "Uploaded audio" : "Recorded"}
                  </p>
                </div>
              </div>
              <div className="voice-actions">
                <Button
                  size="sm"
                  variant="primary"
                  title="Use this voice in Studio"
                  onClick={() => {
                    setActiveVoiceId(p.id);
                    setPage("studio");
                  }}
                >
                  Use Voice
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setDeleteFor(p)}>
                  <Trash2 size={14} aria-hidden="true" /> Delete Voice
                </Button>
              </div>
            </article>
          ))}
        </div>
      )}

      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} title="Create your voice" wide>
        <CreateVoiceFlow
          onComplete={(id) => {
            setCreateOpen(false);
            setActiveVoiceId(id);
          }}
          onCancel={() => setCreateOpen(false)}
        />
      </Dialog>

      {deleteFor ? (
        <DeleteVoiceDialog
          profile={deleteFor}
          open
          onClose={() => setDeleteFor(null)}
          onDeleted={() => setDeleteFor(null)}
        />
      ) : null}
    </div>
  );
}
