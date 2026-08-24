"use client";

import { useEffect } from "react";
import { cx } from "../../lib/cx";

export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  side?: "right" | "left";
}

/** Side panel. Non-blocking by default (backdrop is dismissible), used for the
 * room Help drawer and filter panels. */
export function Drawer({ open, onClose, title, children, side = "right" }: DrawerProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 bg-ink/30" onClick={onClose}>
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
        className={cx(
          "absolute top-0 h-full w-full max-w-sm border-line bg-panel shadow-md",
          side === "right" ? "right-0 border-l" : "left-0 border-r",
        )}
      >
        <div className="flex items-center justify-between border-b border-line px-5 py-3">
          <h2 className="font-display text-md font-semibold text-ink">{title}</h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded-md p-1 text-muted hover:bg-paper hover:text-ink"
          >
            ✕
          </button>
        </div>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
      </aside>
    </div>
  );
}
