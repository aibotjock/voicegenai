import {
  forwardRef,
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

interface FieldShellProps {
  label: string;
  hint?: string;
  children: (id: string) => ReactNode;
}

/** Labeled field shell with proper htmlFor wiring. */
export function FieldShell({ label, hint, children }: FieldShellProps) {
  const id = useId();
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>
        {label}
      </label>
      {children(id)}
      {hint ? <p className="field-hint">{hint}</p> : null}
    </div>
  );
}

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  hint?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  function Input({ label, hint, ...rest }, ref) {
    return (
      <FieldShell label={label} hint={hint}>
        {(id) => <input ref={ref} id={id} className="input" {...rest} />}
      </FieldShell>
    );
  },
);

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  hint?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  function Textarea({ label, hint, ...rest }, ref) {
    if (!label) {
      return <textarea ref={ref} className="textarea" {...rest} />;
    }
    return (
      <FieldShell label={label} hint={hint}>
        {(id) => <textarea ref={ref} id={id} className="textarea" {...rest} />}
      </FieldShell>
    );
  },
);

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string;
  hint?: string;
  children: ReactNode;
}

export function Select({ label, hint, children, ...rest }: SelectProps) {
  return (
    <FieldShell label={label} hint={hint}>
      {(id) => (
        <select id={id} className="select" {...rest}>
          {children}
        </select>
      )}
    </FieldShell>
  );
}
