import { useMemo } from "react";
import { estimateSpeechSeconds, formatDuration, wordCount } from "../../lib/format";
import "./studio.css";

interface ScriptEditorProps {
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
}

/**
 * The Studio writing surface. Deliberately uncluttered: comfortable type,
 * word count, rough duration estimate. Advanced script handling lives in
 * the Pronunciation tool, not here.
 */
export function ScriptEditor({ value, onChange, disabled }: ScriptEditorProps) {
  const words = useMemo(() => wordCount(value), [value]);
  const estSeconds = useMemo(() => estimateSpeechSeconds(words), [words]);

  return (
    <div className="script-editor">
      <label className="sr-only" htmlFor="script-editor">
        Script
      </label>
      <textarea
        id="script-editor"
        className="script-textarea"
        placeholder="What would you like your voice to say?"
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        rows={10}
        spellCheck
      />
      <div className="script-foot">
        <span>
          {words} {words === 1 ? "word" : "words"}
        </span>
        <span>
          {words > 0 ? `≈ ${formatDuration(estSeconds)} of speech` : "Paste or write your script"}
        </span>
      </div>
    </div>
  );
}
