"use client";

import { forwardRef } from "react";
import { cx } from "../../lib/cx";
import { Tooltip } from "./Tooltip";

type Variant = "primary" | "secondary" | "danger" | "ghost";
type Size = "sm" | "md";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  /** When set, the button is disabled AND a tooltip names why (FRONTEND.md rule 2). */
  disabledReason?: string;
}

const BASE =
  "inline-flex items-center justify-center gap-2 rounded-md font-body font-medium " +
  "transition-colors select-none disabled:cursor-not-allowed";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-white hover:bg-accent-strong disabled:bg-line disabled:text-muted",
  secondary:
    "bg-panel text-ink border border-line hover:bg-paper disabled:text-muted disabled:bg-panel",
  danger: "bg-rust text-white hover:opacity-90 disabled:bg-line disabled:text-muted",
  ghost: "bg-transparent text-ink hover:bg-paper disabled:text-muted",
};

// md meets the 44px minimum touch target; sm (36px) is for dense org tables
const SIZES: Record<Size, string> = {
  sm: "h-9 px-3 text-sm",
  md: "h-11 px-4 text-base",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", loading, disabledReason, disabled, children, className, ...rest },
  ref,
) {
  const isDisabled = disabled || loading || !!disabledReason;
  const btn = (
    <button
      ref={ref}
      disabled={isDisabled}
      aria-busy={loading || undefined}
      aria-disabled={isDisabled || undefined}
      className={cx(BASE, VARIANTS[variant], SIZES[size], className)}
      {...rest}
    >
      {loading && (
        <span
          aria-hidden
          className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
      )}
      {children}
    </button>
  );
  // A disabled-with-reason button still needs a hover target for its tooltip,
  // so wrap it (disabled elements don't fire mouse events on their own).
  return disabledReason ? (
    <Tooltip label={disabledReason}>
      <span className="inline-flex">{btn}</span>
    </Tooltip>
  ) : (
    btn
  );
});
