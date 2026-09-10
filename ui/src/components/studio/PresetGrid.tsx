import { Check } from "lucide-react";
import { usePresets } from "../../lib/api/hooks";
import { Spinner } from "../ui/Feedback";
import "./studio.css";

interface PresetGridProps {
  selected: string | null;
  onSelect: (presetId: string) => void;
}

/** Preferred display order for well-known presets; anything else appends. */
const ORDER = ["podcast", "keynote", "boardroom", "calm-expert", "rehearsal-raw"];

/**
 * Voice-style presets rendered from the backend — the API is the source of
 * truth for availability, names and descriptions. Architecture leaves room
 * for future A/B preview without inventing backend features now.
 */
export function PresetGrid({ selected, onSelect }: PresetGridProps) {
  const { data: presets, isLoading, isError } = usePresets();

  if (isLoading) {
    return (
      <div style={{ display: "flex", gap: 8, alignItems: "center", color: "var(--text-3)" }}>
        <Spinner /> Loading styles…
      </div>
    );
  }
  if (isError || !presets) {
    return <p className="field-hint">Styles are unavailable while the voice engine is offline.</p>;
  }

  const ids = Object.keys(presets).sort((a, b) => {
    const ia = ORDER.indexOf(a);
    const ib = ORDER.indexOf(b);
    return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib);
  });

  return (
    <div className="preset-grid" role="group" aria-label="Voice style">
      {ids.map((id) => {
        const p = presets[id];
        const active = selected === id;
        return (
          <button
            key={id}
            type="button"
            className="preset-card"
            aria-pressed={active}
            onClick={() => onSelect(id)}
          >
            <span className="preset-name">
              {p.name}
              {active ? (
                <Check size={16} style={{ color: "var(--accent)" }} aria-hidden="true" />
              ) : null}
            </span>
            <span className="preset-character">{p.character}</span>
          </button>
        );
      })}
    </div>
  );
}
