import { useState, type ReactNode } from "react";
import { ChevronRight } from "lucide-react";

interface CollapsibleProps {
  title: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
}

/** Progressive disclosure wrapper with an accessible trigger. */
export function Collapsible({ title, children, defaultOpen = false }: CollapsibleProps) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <button
        type="button"
        className="collapsible-trigger"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <ChevronRight size={14} className="collapsible-chevron" aria-hidden="true" />
        {title}
      </button>
      {open ? <div className="collapsible-panel">{children}</div> : null}
    </div>
  );
}
