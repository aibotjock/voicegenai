import type { ReactNode } from "react";

export function Spinner({ large = false }: { large?: boolean }) {
  return (
    <span
      className={large ? "spinner spinner-lg" : "spinner"}
      role="status"
      aria-label="Loading"
    />
  );
}

export function Progress({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div
      className="progress"
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div className="progress-fill" style={{ width: `${pct}%` }} />
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  body,
  action,
}: {
  icon?: ReactNode;
  title: string;
  body?: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      {icon ? <div className="empty-icon" aria-hidden="true">{icon}</div> : null}
      <p className="empty-title">{title}</p>
      {body ? <p className="empty-body">{body}</p> : null}
      {action}
    </div>
  );
}
