import type { ReactNode } from "react";

type Tone = "success" | "warning" | "danger" | "info" | "neutral";

interface BadgeProps {
  tone?: Tone;
  /** Show a small dot before the label (status indicators). */
  dot?: boolean;
  children: ReactNode;
}

export function Badge({ tone = "neutral", dot = false, children }: BadgeProps) {
  return (
    <span className={`badge badge-${tone}`}>
      {dot ? <span className="badge-dot" aria-hidden="true" /> : null}
      {children}
    </span>
  );
}
