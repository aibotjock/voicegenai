import { useEngines } from "../../lib/api/hooks";
import { Collapsible } from "../ui/Collapsible";
import { Slider, Switch } from "../ui/Slider";
import "./studio.css";

/**
 * Advanced generation controls.
 *
 * Only options the backend actually accepts on POST /api/v1/generate are
 * exposed here (engine, seed, loudness target, accuracy check). The control
 * list is config-driven so DSP fine-controls (pace/pitch/formant/EQ/dynamics)
 * can slot in when the API learns to accept them — until then they are
 * intentionally not shown, so the UI can never send invalid parameters.
 */
export interface AdvancedOptions {
  engine: string | null; // null = configured default
  seed: number;
  lufs: number | null; // null = preset default
  checkWer: boolean;
}

export const DEFAULT_ADVANCED: AdvancedOptions = {
  engine: null,
  seed: 1234,
  lufs: null,
  checkWer: true,
};

// Loudness bounds used by the shipped presets (-23 broadcast / -16 digital);
// the UI keeps a conservative window inside common practice.
export const LUFS_MIN = -30;
export const LUFS_MAX = -10;

interface AdvancedPanelProps {
  value: AdvancedOptions;
  onChange: (v: AdvancedOptions) => void;
  onReset: () => void;
}

export function AdvancedPanel({ value, onChange, onReset }: AdvancedPanelProps) {
  const { data: engines } = useEngines();
  const usableEngines = (engines ?? []).filter((e) => !e.test_only);

  return (
    <Collapsible title="Advanced">
      <div style={{ display: "flex", flexDirection: "column", gap: 16, paddingTop: 8 }}>
        {usableEngines.length > 1 ? (
          <div className="field">
            <label className="field-label" htmlFor="adv-engine">
              Voice engine
            </label>
            <select
              id="adv-engine"
              className="select"
              value={value.engine ?? ""}
              onChange={(e) => onChange({ ...value, engine: e.target.value || null })}
            >
              <option value="">Default (recommended)</option>
              {usableEngines.map((e) => (
                <option key={e.id} value={e.id} disabled={Boolean(e.error)}>
                  {engineDisplayName(e.id)}
                  {e.error ? " — unavailable" : ""}
                </option>
              ))}
            </select>
            <p className="field-hint">Most people should leave this on Default.</p>
          </div>
        ) : null}

        <Slider
          label="Loudness target"
          min={LUFS_MIN}
          max={LUFS_MAX}
          step={0.5}
          value={value.lufs ?? -16}
          format={(v) => (value.lufs === null ? "Style default" : `${v.toFixed(1)} LUFS`)}
          onChange={(v) => onChange({ ...value, lufs: v })}
          hint="-16 LUFS suits online video and podcasts; -23 suits broadcast."
        />
        {value.lufs !== null ? (
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            style={{ alignSelf: "flex-start" }}
            onClick={() => onChange({ ...value, lufs: null })}
          >
            Use style default loudness
          </button>
        ) : null}

        <div className="field">
          <label className="field-label" htmlFor="adv-seed">
            Variation seed
          </label>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              id="adv-seed"
              className="input"
              type="number"
              min={0}
              max={999999}
              value={value.seed}
              onChange={(e) => {
                const n = Number(e.target.value);
                if (Number.isInteger(n) && n >= 0 && n <= 999999) {
                  onChange({ ...value, seed: n });
                }
              }}
              style={{ maxWidth: 140 }}
            />
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => onChange({ ...value, seed: Math.floor(Math.random() * 100000) })}
            >
              Randomize
            </button>
          </div>
          <p className="field-hint">Same script + seed gives the same result.</p>
        </div>

        <Switch
          label="Accuracy self-check"
          checked={value.checkWer}
          onChange={(v) => onChange({ ...value, checkWer: v })}
          hint="Recommended. Each section is transcribed and compared to your script; mismatches are retried and flagged."
        />

        <div>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onReset}>
            Reset to preset defaults
          </button>
        </div>
      </div>
    </Collapsible>
  );
}

/** Friendly display names for known engine ids (presentation only). */
export function engineDisplayName(id: string): string {
  switch (id) {
    case "chatterbox":
      return "Chatterbox";
    case "cosyvoice3":
      return "CosyVoice 3";
    case "qwen3-tts":
      return "Qwen3 TTS";
    case "offline-stub":
      return "Offline test engine";
    default:
      return id;
  }
}
