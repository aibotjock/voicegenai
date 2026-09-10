import { useEffect, useState } from "react";
import { AudioLines, KeyRound } from "lucide-react";
import { PRODUCT_NAME } from "./lib/brand";
import {
  bootstrapConnection,
  connectViaDevToken,
  connection,
  isTauri,
  listenSidecarEvents,
  restartViaTauri,
} from "./lib/sidecar/connection";
import { useApp } from "./lib/state/AppContext";
import { useProfiles } from "./lib/api/hooks";
import { AppShell } from "./components/layout/AppShell";
import { OnboardingFlow } from "./components/onboarding/OnboardingFlow";
import { StudioPage } from "./pages/StudioPage";
import { VoicesPage } from "./pages/VoicesPage";
import { LibraryPage } from "./pages/LibraryPage";
import { SettingsPage } from "./pages/SettingsPage";
import { Button } from "./components/ui/Button";
import { Toaster } from "./components/ui/Toaster";
import { Spinner } from "./components/ui/Feedback";

/**
 * Root: connection lifecycle → onboarding gate → app shell + page switch.
 */
export default function App() {
  const { sidecar, page } = useApp();
  const [booted, setBooted] = useState(false);
  const [onboarded, setOnboarded] = useState(false);

  useEffect(() => {
    let alive = true;
    let unlisten: (() => void) | undefined;
    void listenSidecarEvents().then((u) => {
      unlisten = u;
    });
    void bootstrapConnection().finally(() => {
      if (alive) setBooted(true);
    });
    return () => {
      alive = false;
      unlisten?.();
    };
  }, []);

  if (!booted || sidecar.status === "connecting") {
    return (
      <FullPage>
        <Spinner large />
        <h1>Starting Voice Engine…</h1>
        <p>The local voice engine runs on this device only.</p>
      </FullPage>
    );
  }

  if (sidecar.status === "needs-credentials") {
    return <DevConnectScreen />;
  }

  if (sidecar.status === "offline") {
    return <OfflineScreen />;
  }

  return (
    <>
      {onboarded ? (
        <AppShell>
          {page === "studio" && <StudioPage />}
          {page === "voices" && <VoicesPage />}
          {page === "library" && <LibraryPage />}
          {page === "settings" && <SettingsPage />}
        </AppShell>
      ) : (
        <OnboardingGate onDone={() => setOnboarded(true)} />
      )}
      <HealthWatcher />
      <Toaster />
    </>
  );
}

/** Shows onboarding only when there really is no voice profile yet. */
function OnboardingGate({ onDone }: { onDone: () => void }) {
  const { data: profiles, isLoading } = useProfiles();
  const hasVoices = !isLoading && !!profiles && profiles.length > 0;

  useEffect(() => {
    if (hasVoices) onDone(); // voices exist — go straight to Studio
  }, [hasVoices, onDone]);

  if (isLoading) {
    return (
      <FullPage>
        <Spinner large />
      </FullPage>
    );
  }
  if (!profiles || profiles.length === 0) {
    return <OnboardingFlow onDone={onDone} />;
  }
  return null;
}

/** Keeps the connection pill honest if the sidecar dies mid-session. */
function HealthWatcher() {
  const { sidecar } = useApp();
  useEffect(() => {
    if (sidecar.status !== "ready") return;
    const t = window.setInterval(() => void connection.revalidate(), 15_000);
    return () => window.clearInterval(t);
  }, [sidecar.status]);
  return null;
}

function FullPage({ children }: { children: React.ReactNode }) {
  return (
    <div className="fullpage-state" role="status">
      <span className="onboarding-mark" aria-hidden="true">
        <AudioLines size={26} />
      </span>
      {children}
    </div>
  );
}

function OfflineScreen() {
  const [working, setWorking] = useState(false);
  return (
    <FullPage>
      <h1>Voice Engine Offline</h1>
      <p>
        The local voice engine is not responding. Your data is safe on this device.
      </p>
      {isTauri() ? (
        <Button
          variant="primary"
          disabled={working}
          onClick={async () => {
            setWorking(true);
            await restartViaTauri().catch(() => undefined);
            setWorking(false);
          }}
        >
          {working ? "Restarting…" : "Restart Voice Engine"}
        </Button>
      ) : (
        <p className="connect-code">
          Start the sidecar, then reload:
          {"\n"}$ presence sidecar --port 8765
        </p>
      )}
    </FullPage>
  );
}

/**
 * Browser-dev connect screen. The token comes from the sidecar launch line
 * and is held in memory only — never written to web storage.
 */
function DevConnectScreen() {
  const [token, setToken] = useState("");
  const [working, setWorking] = useState(false);
  const [failed, setFailed] = useState(false);

  const connect = async () => {
    setWorking(true);
    setFailed(false);
    const ok = await connectViaDevToken(token.trim());
    setWorking(false);
    if (!ok) setFailed(true);
  };

  return (
    <FullPage>
      <h1>Connect to Voice Engine</h1>
      <p>
        Development mode: start the sidecar and paste the token it prints at launch.
        The token is kept in memory for this session only.
      </p>
      <div className="connect-form">
        <p className="connect-code">
          $ presence sidecar{"\n"}PRESENCE_SIDECAR_READY token=… port=8765
        </p>
        <label className="field-label" htmlFor="dev-token">
          <KeyRound size={13} aria-hidden="true" style={{ verticalAlign: "-2px" }} /> Sidecar token
        </label>
        <input
          id="dev-token"
          className="input"
          type="password"
          autoComplete="off"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && token.trim() && connect()}
          placeholder="Paste token"
        />
        {failed ? (
          <p role="alert" style={{ color: "var(--danger)", fontSize: "var(--text-sm)" }}>
            Could not connect — check the token and that the sidecar is running on the proxied
            port.
          </p>
        ) : null}
        <Button variant="primary" disabled={!token.trim() || working} onClick={() => void connect()}>
          {working ? "Connecting…" : `Connect to ${PRODUCT_NAME}`}
        </Button>
      </div>
    </FullPage>
  );
}
