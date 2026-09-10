import { useState, type ReactNode } from "react";
import {
  AudioLines,
  FolderOpen,
  Mic,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  ShieldCheck,
} from "lucide-react";
import { PRODUCT_NAME } from "../../lib/brand";
import { useApp, type Page } from "../../lib/state/AppContext";
import { restartViaTauri, isTauri } from "../../lib/sidecar/connection";
import { Button } from "../ui/Button";
import { Spinner } from "../ui/Feedback";
import "./appShell.css";

const NAV: Array<{ id: Page; label: string; icon: typeof Mic }> = [
  { id: "studio", label: "Studio", icon: AudioLines },
  { id: "voices", label: "Voices", icon: Mic },
  { id: "library", label: "Library", icon: FolderOpen },
  { id: "settings", label: "Settings", icon: Settings },
];

function ConnectionPill() {
  const { sidecar, toast } = useApp();
  const [restarting, setRestarting] = useState(false);

  if (sidecar.status === "ready") {
    return (
      <span className="conn-pill conn-ready" title="The local voice engine is running">
        <span className="conn-dot" aria-hidden="true" />
        Voice Engine Ready
      </span>
    );
  }
  if (sidecar.status === "connecting") {
    return (
      <span className="conn-pill conn-starting">
        <span className="conn-dot" aria-hidden="true" />
        Starting Voice Engine…
      </span>
    );
  }
  if (sidecar.status === "needs-credentials") {
    return (
      <span className="conn-pill conn-starting">
        <span className="conn-dot" aria-hidden="true" />
        Connect to Voice Engine
      </span>
    );
  }
  return (
    <span className="conn-pill conn-offline">
      <span className="conn-dot" aria-hidden="true" />
      Voice Engine Offline
      {isTauri() ? (
        <Button
          size="sm"
          variant="ghost"
          disabled={restarting}
          onClick={async () => {
            setRestarting(true);
            const ok = await restartViaTauri().catch(() => false);
            setRestarting(false);
            if (!ok) toast("error", "Could not restart the voice engine.");
          }}
        >
          {restarting ? <Spinner /> : "Restart"}
        </Button>
      ) : null}
    </span>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { page, setPage } = useApp();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className={collapsed ? "shell shell-collapsed" : "shell"}>
      <header className="topbar">
        <div className="topbar-brand">
          <span className="topbar-brand-mark" aria-hidden="true">
            <AudioLines size={16} />
          </span>
          <span className="brand-name">{PRODUCT_NAME}</span>
        </div>
        <div className="topbar-spacer" />
        <ConnectionPill />
      </header>

      <nav className="sidebar" aria-label="Primary">
        {NAV.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            className="nav-item"
            aria-current={page === id ? "page" : undefined}
            onClick={() => setPage(id)}
            title={label}
          >
            <Icon size={18} aria-hidden="true" />
            <span className="nav-label">{label}</span>
          </button>
        ))}
        <div className="sidebar-foot">
          <button
            type="button"
            className="nav-item"
            onClick={() => setCollapsed((c) => !c)}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? (
              <PanelLeftOpen size={18} aria-hidden="true" />
            ) : (
              <PanelLeftClose size={18} aria-hidden="true" />
            )}
            <span className="nav-label">Collapse</span>
          </button>
          <div className="privacy-note" title="All processing happens on this device">
            <ShieldCheck size={14} aria-hidden="true" />
            <span>Processing locally</span>
          </div>
        </div>
      </nav>

      <main className="content">
        <div className="content-inner">{children}</div>
      </main>
    </div>
  );
}
