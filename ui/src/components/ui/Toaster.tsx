import { CheckCircle2, Info, XCircle, X } from "lucide-react";
import { useApp } from "../../lib/state/AppContext";

const ICONS = {
  info: Info,
  success: CheckCircle2,
  error: XCircle,
} as const;

export function Toaster() {
  const { toasts, dismissToast } = useApp();
  if (toasts.length === 0) return null;
  return (
    <div className="toaster" aria-live="polite" aria-label="Notifications">
      {toasts.map((t) => {
        const Icon = ICONS[t.kind];
        return (
          <div key={t.id} className={`toast toast-${t.kind}`} role="status">
            <Icon size={16} aria-hidden="true" style={{ flexShrink: 0, marginTop: 2 }} />
            <span style={{ flex: 1 }}>{t.message}</span>
            <button
              type="button"
              className="btn btn-icon btn-sm"
              aria-label="Dismiss notification"
              onClick={() => dismissToast(t.id)}
            >
              <X size={14} aria-hidden="true" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
