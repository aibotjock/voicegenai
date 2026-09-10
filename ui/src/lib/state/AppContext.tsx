/**
 * Application/session state (UI state only — server truth stays in React
 * Query and the backend). Kept deliberately small: navigation, active voice,
 * session generation list, toasts, theme, and the sidecar connection.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useSyncExternalStore } from "react";
import { SidecarClient } from "../api/client";
import {
  connection,
  type SidecarSnapshot,
} from "../sidecar/connection";

export type Page = "studio" | "voices" | "library" | "settings";
export type Theme = "system" | "light" | "dark";

export interface Toast {
  id: number;
  kind: "info" | "success" | "error";
  message: string;
}

/** One completed generation this session (Library → Recent Session). */
export interface SessionGeneration {
  jobId: string;
  createdAt: string;
  voiceName: string;
  designName: string;
  scriptExcerpt: string;
  segments: number;
  flagged: number;
  elapsedS: number | null;
  /** Set after a successful export. */
  exportMasterPath?: string;
  exportStem?: string;
}

interface AppContextValue {
  page: Page;
  setPage: (p: Page) => void;
  client: SidecarClient | null;
  sidecar: SidecarSnapshot;
  activeVoiceId: string | null;
  setActiveVoiceId: (id: string | null) => void;
  toasts: Toast[];
  toast: (kind: Toast["kind"], message: string) => void;
  dismissToast: (id: number) => void;
  sessionGenerations: SessionGeneration[];
  addSessionGeneration: (g: SessionGeneration) => void;
  updateSessionGeneration: (jobId: string, patch: Partial<SessionGeneration>) => void;
  theme: Theme;
  setTheme: (t: Theme) => void;
}

const Ctx = createContext<AppContextValue | null>(null);

const THEME_KEY = "voicegenai.theme";
const VOICE_KEY = "voicegenai.activeVoiceId";

/** Web storage can be missing (privacy modes, tests) — never crash on it. */
const storage = {
  get(key: string): string | null {
    try {
      return window.localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  set(key: string, value: string): void {
    try {
      window.localStorage.setItem(key, value);
    } catch {
      /* unavailable */
    }
  },
  remove(key: string): void {
    try {
      window.localStorage.removeItem(key);
    } catch {
      /* unavailable */
    }
  },
};

export function AppProvider({ children }: { children: ReactNode }) {
  const [page, setPage] = useState<Page>("studio");
  const [activeVoiceId, setActiveVoiceIdState] = useState<string | null>(() =>
    storage.get(VOICE_KEY),
  );
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [sessionGenerations, setSessionGenerations] = useState<SessionGeneration[]>([]);
  const [theme, setThemeState] = useState<Theme>(() => {
    const t = storage.get(THEME_KEY);
    return t === "light" || t === "dark" ? t : "system";
  });
  const toastId = useRef(0);

  const sidecar = useSyncExternalStore(
    (cb) => connection.subscribe(cb),
    () => connection.getSnapshot(),
  );

  // Theme: explicit choice wins; "system" follows the OS.
  useEffect(() => {
    const root = document.documentElement;
    const apply = () => {
      const dark =
        theme === "dark" ||
        (theme === "system" &&
          window.matchMedia("(prefers-color-scheme: dark)").matches);
      root.dataset.theme = dark ? "dark" : "light";
    };
    apply();
    storage.set(THEME_KEY, theme);
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [theme]);

  const setTheme = useCallback((t: Theme) => setThemeState(t), []);

  const setActiveVoiceId = useCallback((id: string | null) => {
    setActiveVoiceIdState(id);
    if (id) storage.set(VOICE_KEY, id);
    else storage.remove(VOICE_KEY);
  }, []);

  const dismissToast = useCallback((id: number) => {
    setToasts((ts) => ts.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback(
    (kind: Toast["kind"], message: string) => {
      const id = ++toastId.current;
      setToasts((ts) => [...ts, { id, kind, message }]);
      window.setTimeout(() => dismissToast(id), kind === "error" ? 8000 : 4500);
    },
    [dismissToast],
  );

  const addSessionGeneration = useCallback((g: SessionGeneration) => {
    setSessionGenerations((gs) => [g, ...gs]);
  }, []);

  const updateSessionGeneration = useCallback(
    (jobId: string, patch: Partial<SessionGeneration>) => {
      setSessionGenerations((gs) =>
        gs.map((g) => (g.jobId === jobId ? { ...g, ...patch } : g)),
      );
    },
    [],
  );

  const value = useMemo<AppContextValue>(
    () => ({
      page,
      setPage,
      client: connection.getClient(),
      sidecar,
      activeVoiceId,
      setActiveVoiceId,
      toasts,
      toast,
      dismissToast,
      sessionGenerations,
      addSessionGeneration,
      updateSessionGeneration,
      theme,
      setTheme,
    }),
    [
      page,
      sidecar,
      activeVoiceId,
      setActiveVoiceId,
      toasts,
      toast,
      dismissToast,
      sessionGenerations,
      addSessionGeneration,
      updateSessionGeneration,
      theme,
      setTheme,
    ],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): AppContextValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp must be used inside <AppProvider>");
  return v;
}
