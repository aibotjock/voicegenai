import { useState } from "react";
import { Plus, X } from "lucide-react";
import type { GlossaryItem } from "../../lib/api/types";
import { Button } from "../ui/Button";
import { Collapsible } from "../ui/Collapsible";
import "./studio.css";

interface PronunciationEditorProps {
  value: GlossaryItem[];
  onChange: (items: GlossaryItem[]) => void;
}

/**
 * Lightweight pronunciation tool for names, brands, acronyms and unusual
 * words. Phoneme-level control stays in an expert field per entry.
 */
export function PronunciationEditor({ value, onChange }: PronunciationEditorProps) {
  const [term, setTerm] = useState("");
  const [sayAs, setSayAs] = useState("");
  const [phonemes, setPhonemes] = useState("");

  const add = () => {
    const t = term.trim();
    if (!t) return;
    const item: GlossaryItem = { term: t };
    if (phonemes.trim()) item.phonemes = phonemes.trim();
    else if (sayAs.trim()) item.say_as = sayAs.trim();
    onChange([...value.filter((g) => g.term.toLowerCase() !== t.toLowerCase()), item]);
    setTerm("");
    setSayAs("");
    setPhonemes("");
  };

  return (
    <div className="pron-panel">
      <Collapsible title={`Pronunciations${value.length > 0 ? ` (${value.length})` : ""}`}>
        <p className="field-hint" style={{ marginBottom: 8 }}>
          Tell the voice how to say names, brands or technical words.
        </p>

        {value.length > 0 ? (
          <div className="pron-list" aria-label="Pronunciation list">
            {value.map((g) => (
              <span key={g.term} className="pron-tag">
                <strong>{g.term}</strong>
                <span aria-hidden="true">→</span>
                <span>{g.phonemes ? `[${g.phonemes}]` : g.say_as}</span>
                <button
                  type="button"
                  className="btn btn-icon btn-sm"
                  aria-label={`Remove pronunciation for ${g.term}`}
                  onClick={() => onChange(value.filter((x) => x.term !== g.term))}
                >
                  <X size={12} aria-hidden="true" />
                </button>
              </span>
            ))}
          </div>
        ) : null}

        <div className="pron-row">
          <label className="sr-only" htmlFor="pron-term">
            Word
          </label>
          <input
            id="pron-term"
            className="input"
            placeholder='Word, e.g. "Qwen"'
            value={term}
            onChange={(e) => setTerm(e.target.value)}
          />
          <label className="sr-only" htmlFor="pron-say">
            Say as
          </label>
          <input
            id="pron-say"
            className="input"
            placeholder='Say as, e.g. "kwen"'
            value={sayAs}
            onChange={(e) => setSayAs(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && add()}
          />
          <Button size="sm" onClick={add} disabled={!term.trim() || (!sayAs.trim() && !phonemes.trim())}>
            <Plus size={14} aria-hidden="true" /> Add
          </Button>
        </div>
        <details style={{ marginTop: 8 }}>
          <summary className="field-hint" style={{ cursor: "pointer" }}>
            Expert: phoneme input (ARPAbet)
          </summary>
          <div className="pron-row" style={{ marginTop: 8, gridTemplateColumns: "1fr auto" }}>
            <label className="sr-only" htmlFor="pron-phonemes">
              Phonemes
            </label>
            <input
              id="pron-phonemes"
              className="input"
              placeholder="Phonemes, e.g. K W EH1 N"
              value={phonemes}
              onChange={(e) => setPhonemes(e.target.value)}
            />
          </div>
        </details>
      </Collapsible>
    </div>
  );
}
