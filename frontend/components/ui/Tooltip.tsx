"use client";

import { useId, useState } from "react";
import { cx } from "../../lib/cx";

export interface TooltipProps {
  label: string;
  children: React.ReactNode;
  side?: "top" | "bottom";
}

/** Lightweight hover/focus tooltip. Accessible: the trigger references the
 * tip via aria-describedby, and it appears on keyboard focus too. */
export function Tooltip({ label, children, side = "top" }: TooltipProps) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocusCapture={() => setOpen(true)}
      onBlurCapture={() => setOpen(false)}
      aria-describedby={open ? id : undefined}
    >
      {children}
      {open && (
        <span
          role="tooltip"
          id={id}
          className={cx(
            "pointer-events-none absolute left-1/2 z-50 w-max max-w-64 -translate-x-1/2 rounded-md bg-ink px-2 py-1 text-xs text-white shadow-md",
            side === "top" ? "bottom-full mb-2" : "top-full mt-2",
          )}
        >
          {label}
        </span>
      )}
    </span>
  );
}
