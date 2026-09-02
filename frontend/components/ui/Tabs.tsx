"use client";

import { cx } from "../../lib/cx";

export interface TabItem {
  id: string;
  label: string;
  count?: number;
}

export interface TabsProps {
  tabs: TabItem[];
  active: string;
  onChange: (id: string) => void;
}

/** Accessible tab strip (role=tablist). Callers render the active panel. */
export function Tabs({ tabs, active, onChange }: TabsProps) {
  return (
    <div role="tablist" className="flex gap-1 border-b border-line">
      {tabs.map((t) => {
        const selected = t.id === active;
        return (
          <button
            key={t.id}
            role="tab"
            aria-selected={selected}
            onClick={() => onChange(t.id)}
            className={cx(
              "-mb-px border-b-2 px-3 py-2 text-base font-medium transition-colors",
              selected
                ? "border-accent text-ink"
                : "border-transparent text-muted hover:text-ink",
            )}
          >
            {t.label}
            {typeof t.count === "number" && (
              <span
                className={cx(
                  "ml-1.5 rounded-full px-1.5 py-0.5 text-xs",
                  selected ? "bg-accent-tint text-accent" : "bg-paper text-muted",
                )}
              >
                {t.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
