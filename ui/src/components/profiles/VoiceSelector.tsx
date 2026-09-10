import { Plus } from "lucide-react";
import { useProfiles } from "../../lib/api/hooks";
import { useApp } from "../../lib/state/AppContext";
import { Button } from "../ui/Button";
import "./profiles.css";

interface VoiceSelectorProps {
  onCreateVoice: () => void;
}

/**
 * Studio voice selector: quick switching between profiles.
 * If there is no voice at all, the only action offered is Create Voice.
 */
export function VoiceSelector({ onCreateVoice }: VoiceSelectorProps) {
  const { activeVoiceId, setActiveVoiceId } = useApp();
  const { data: profiles } = useProfiles();

  if (profiles && profiles.length === 0) {
    return (
      <div className="voice-selector">
        <span className="field-label">Voice</span>
        <Button variant="primary" size="sm" onClick={onCreateVoice}>
          <Plus size={14} aria-hidden="true" /> Create Voice
        </Button>
      </div>
    );
  }

  return (
    <div className="voice-selector">
      <label className="field-label" htmlFor="voice-select">
        Voice
      </label>
      <select
        id="voice-select"
        className="select"
        value={activeVoiceId ?? ""}
        onChange={(e) => setActiveVoiceId(e.target.value || null)}
      >
        <option value="" disabled>
          Select a voice
        </option>
        {(profiles ?? []).map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
      <Button variant="ghost" size="sm" onClick={onCreateVoice}>
        <Plus size={14} aria-hidden="true" /> New voice
      </Button>
    </div>
  );
}
