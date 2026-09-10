interface SliderProps {
  id?: string;
  label: string;
  min: number;
  max: number;
  step?: number;
  value: number;
  onChange: (v: number) => void;
  /** Formatted value shown at the right, e.g. "-16.0 LUFS". */
  format?: (v: number) => string;
  disabled?: boolean;
  /** Secondary technical note shown under the label. */
  hint?: string;
}

export function Slider({
  id,
  label,
  min,
  max,
  step = 1,
  value,
  onChange,
  format,
  disabled,
  hint,
}: SliderProps) {
  const inputId = id ?? `slider-${label.replace(/\s+/g, "-").toLowerCase()}`;
  return (
    <div className="field">
      <div className="slider-row">
        <label className="field-label" htmlFor={inputId}>
          {label}
        </label>
        <span className="slider-value">{format ? format(value) : value}</span>
      </div>
      <input
        id={inputId}
        className="slider"
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-valuetext={format ? format(value) : String(value)}
      />
      {hint ? <p className="field-hint">{hint}</p> : null}
    </div>
  );
}

interface SwitchProps {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  hint?: string;
  disabled?: boolean;
}

export function Switch({ label, checked, onChange, hint, disabled }: SwitchProps) {
  return (
    <div className="slider-row" style={{ gridTemplateColumns: "1fr auto" }}>
      <div>
        <span className="field-label">{label}</span>
        {hint ? <p className="field-hint">{hint}</p> : null}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        className="switch"
        disabled={disabled}
        onClick={() => onChange(!checked)}
      />
    </div>
  );
}
