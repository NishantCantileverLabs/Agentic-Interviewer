"use client";

import { forwardRef, useId } from "react";
import { cx } from "../../lib/cx";

const FIELD =
  "w-full rounded-md border border-line bg-panel px-3 py-2 text-base text-ink " +
  "placeholder:text-muted focus-visible:border-accent disabled:bg-paper disabled:text-muted";

interface Labelled {
  label: string;
  error?: string;
  hint?: string;
}

function Wrap({
  id,
  label,
  error,
  hint,
  children,
}: Labelled & { id: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-ink-soft">
        {label}
      </label>
      {children}
      {hint && !error && <span className="text-xs text-muted">{hint}</span>}
      {error && (
        <span role="alert" className="text-xs text-rust">
          {error}
        </span>
      )}
    </div>
  );
}

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement>,
    Labelled {}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, error, hint, className, id, ...rest },
  ref,
) {
  const gen = useId();
  const fieldId = id ?? gen;
  return (
    <Wrap id={fieldId} label={label} error={error} hint={hint}>
      <input
        ref={ref}
        id={fieldId}
        aria-invalid={!!error}
        className={cx(FIELD, error && "border-rust", className)}
        {...rest}
      />
    </Wrap>
  );
});

export interface SelectProps
  extends React.SelectHTMLAttributes<HTMLSelectElement>,
    Labelled {
  options: { value: string; label: string }[];
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, error, hint, options, className, id, ...rest },
  ref,
) {
  const gen = useId();
  const fieldId = id ?? gen;
  return (
    <Wrap id={fieldId} label={label} error={error} hint={hint}>
      <select
        ref={ref}
        id={fieldId}
        aria-invalid={!!error}
        className={cx(FIELD, "appearance-none", error && "border-rust", className)}
        {...rest}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </Wrap>
  );
});

export interface CheckboxProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> {
  label: React.ReactNode;
  error?: string;
}

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox(
  { label, error, className, id, ...rest },
  ref,
) {
  const gen = useId();
  const fieldId = id ?? gen;
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={fieldId} className="flex items-start gap-2.5 text-base text-ink">
        <input
          ref={ref}
          id={fieldId}
          type="checkbox"
          className={cx("mt-0.5 h-4 w-4 accent-accent", className)}
          aria-invalid={!!error}
          {...rest}
        />
        <span>{label}</span>
      </label>
      {error && (
        <span role="alert" className="text-xs text-rust">
          {error}
        </span>
      )}
    </div>
  );
});
