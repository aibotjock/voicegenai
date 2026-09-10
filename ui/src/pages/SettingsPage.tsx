import { useMemo, useState } from "react";
import { Download, ShieldCheck } from "lucide-react";
import { useAudit, useDiagnostics, useEngines, useHealth } from "../lib/api/hooks";
import { PRODUCT_NAME, BACKEND_NAME } from "../lib/brand";
import { formatDateTime } from "../lib/format";
import { dataHomeFromDiagnostics } from "../lib/fs/localFiles";
import { useApp, type Theme } from "../lib/state/AppContext";
import { engineDisplayName } from "../components/studio/AdvancedPanel";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Collapsible } from "../components/ui/Collapsible";
import "./pages.css";

type Section = "general" | "engines" | "storage" | "privacy" | "advanced";

const SECTIONS: Array<{ id: Section; label: string }> = [
  { id: "general", label: "General" },
  { id: "engines", label: "Engines" },
  { id: "storage", label: "Storage" },
  { id: "privacy", label: "Privacy" },
  { id: "advanced", label: "Advanced" },
];

export function SettingsPage() {
  const [section, setSection] = useState<Section>("general");
  const { theme, setTheme, sidecar } = useApp();
  const { data: health } = useHealth();
  const { data: engines } = useEngines();
  const { data: diagnostics } = useDiagnostics(section === "storage" || section === "privacy");
  const { data: audit } = useAudit(section === "privacy");

  const home = useMemo(
    () => (diagnostics ? dataHomeFromDiagnostics(diagnostics.bundle) : null),
    [diagnostics],
  );

  return (
    <div>
      <header className="page-head">
        <div>
          <h1 className="page-title">Settings</h1>
          <p className="page-sub">{PRODUCT_NAME} preferences and system status.</p>
        </div>
      </header>

      <div className="settings-grid">
        <nav className="settings-nav" aria-label="Settings sections">
          {SECTIONS.map((s) => (
            <button
              key={s.id}
              type="button"
              className="settings-nav-item"
              aria-current={section === s.id}
              onClick={() => setSection(s.id)}
            >
              {s.label}
            </button>
          ))}
        </nav>

        <div>
          {section === "general" && (
            <section className="settings-section" aria-labelledby="set-general">
              <h2 id="set-general">General</h2>
              <div className="settings-row">
                <div>
                  <div className="settings-row-label">Appearance</div>
                  <div className="settings-row-desc">Choose light, dark, or follow the system.</div>
                </div>
                <label className="sr-only" htmlFor="theme-select">
                  Appearance
                </label>
                <select
                  id="theme-select"
                  className="select"
                  style={{ width: 160 }}
                  value={theme}
                  onChange={(e) => setTheme(e.target.value as Theme)}
                >
                  <option value="system">System</option>
                  <option value="light">Light</option>
                  <option value="dark">Dark</option>
                </select>
              </div>
            </section>
          )}

          {section === "engines" && (
            <section className="settings-section" aria-labelledby="set-engines">
              <h2 id="set-engines">Voice engines</h2>
              <p className="settings-row-desc">
                Engine status is reported live by the voice engine. The default engine is chosen
                by the backend configuration; manual selection lives in Studio → Advanced.
              </p>
              <table className="engine-table">
                <thead>
                  <tr>
                    <th>Engine</th>
                    <th>Model</th>
                    <th>Languages</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {(engines ?? []).map((e) => (
                    <tr key={e.id}>
                      <td>
                        {engineDisplayName(e.id)}
                        {health?.default_engine === e.id ? (
                          <span className="settings-row-desc"> · default</span>
                        ) : null}
                      </td>
                      <td className="kv">{e.model_id || "—"}</td>
                      <td>{e.languages.join(", ") || "—"}</td>
                      <td>
                        {e.test_only ? (
                          <Badge tone="neutral">Testing</Badge>
                        ) : e.error ? (
                          <Badge tone="warning" dot>
                            Unavailable
                          </Badge>
                        ) : (
                          <Badge tone="success" dot>
                            Available
                          </Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          {section === "storage" && (
            <section className="settings-section" aria-labelledby="set-storage">
              <h2 id="set-storage">Storage</h2>
              <p className="settings-row-desc">
                All data stays on this device. Voice recordings and voiceprints are stored
                encrypted.
              </p>
              {home ? (
                <>
                  <div>
                    <div className="settings-row-label">Data folder</div>
                    <p className="kv">{home}</p>
                  </div>
                  <div>
                    <div className="settings-row-label">Exports</div>
                    <p className="kv">{home}/exports</p>
                  </div>
                </>
              ) : (
                <p className="settings-row-desc">
                  Storage paths are reported once the voice engine is running.
                </p>
              )}
            </section>
          )}

          {section === "privacy" && (
            <>
              <section className="settings-section" aria-labelledby="set-privacy">
                <h2 id="set-privacy">Privacy</h2>
                <div className="privacy-chips">
                  <Badge tone="success" dot>
                    Processing locally
                  </Badge>
                  <Badge tone="success" dot>
                    Stored on this device
                  </Badge>
                  <Badge tone="info" dot>
                    Synthetic provenance included
                  </Badge>
                </div>
                <p className="settings-row-desc">
                  <ShieldCheck size={13} aria-hidden="true" style={{ verticalAlign: "-2px" }} />{" "}
                  The voice engine listens on this computer only (127.0.0.1) and performs no
                  network calls. Nothing you record or write leaves this device.
                </p>
                <DiagnosticsDownload />
              </section>

              <section className="settings-section" aria-labelledby="set-audit">
                <h2 id="set-audit">Audit log</h2>
                <p className="settings-row-desc">
                  Local record of security-relevant events. Contains hashes and timestamps — never
                  scripts or audio.
                </p>
                {!audit || audit.length === 0 ? (
                  <p className="settings-row-desc">No events yet.</p>
                ) : (
                  <div className="audit-list">
                    {[...audit].reverse().slice(0, 50).map((a, i) => (
                      <div key={i} className="audit-row">
                        <span className="audit-kind">{a.event}</span>
                        <span>{formatDateTime(a.ts)}</span>
                        {a.text_sha256 ? (
                          <span className="kv">script {a.text_sha256.slice(0, 12)}…</span>
                        ) : null}
                        {a.detail ? <span>{a.detail}</span> : null}
                      </div>
                    ))}
                  </div>
                )}
              </section>
            </>
          )}

          {section === "advanced" && (
            <section className="settings-section" aria-labelledby="set-advanced">
              <h2 id="set-advanced">Advanced</h2>
              <div className="settings-row">
                <div>
                  <div className="settings-row-label">Voice engine connection</div>
                  <div className="settings-row-desc">
                    {sidecar.status === "ready"
                      ? `Connected on port ${sidecar.port ?? "—"} (this device only).`
                      : "Not connected."}
                  </div>
                </div>
                <Badge
                  tone={sidecar.status === "ready" ? "success" : "danger"}
                  dot
                >
                  {sidecar.status === "ready" ? "Ready" : "Offline"}
                </Badge>
              </div>
              {health ? (
                <Collapsible title="Backend details">
                  <p className="kv">
                    {[
                      `sidecar: ${health.app} ${health.version}`,
                      `default_engine: ${health.default_engine}`,
                      `default_design: ${health.default_design}`,
                      `presets: ${health.presets.join(", ")}`,
                    ].join("\n")}
                  </p>
                </Collapsible>
              ) : null}
              <p className="settings-row-desc">
                The access token is generated per launch and never displayed or stored.
              </p>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

function DiagnosticsDownload() {
  const { data: diagnostics } = useDiagnostics();
  const download = () => {
    if (!diagnostics) return;
    const blob = new Blob([diagnostics.bundle], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${BACKEND_NAME.toLowerCase().replace(/\s+/g, "-")}-diagnostics.json`;
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div>
      <Button variant="secondary" size="sm" onClick={download} disabled={!diagnostics}>
        <Download size={14} aria-hidden="true" /> Download diagnostics
      </Button>
      <p className="settings-row-desc" style={{ marginTop: 4 }}>
        Logs and configuration only — no audio, no voiceprints, no scripts.
      </p>
    </div>
  );
}
