"use client";

import { createContext, useCallback, useContext, useState } from "react";
import { cx } from "../../lib/cx";

type ToastTone = "info" | "success" | "error";
interface ToastItem {
  id: number;
  message: string;
  tone: ToastTone;
}

const ToastCtx = createContext<(message: string, tone?: ToastTone) => void>(() => {});

/** Wrap the app once; call useToast() to raise one. Toasts announce via an
 * aria-live region so screen readers hear them. */
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const push = useCallback((message: string, tone: ToastTone = "info") => {
    const id = Date.now() + Math.floor(performance.now());
    setItems((xs) => [...xs, { id, message, tone }]);
    setTimeout(() => setItems((xs) => xs.filter((t) => t.id !== id)), 4000);
  }, []);

  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed bottom-4 right-4 z-[60] flex flex-col gap-2"
      >
        {items.map((t) => (
          <div
            key={t.id}
            className={cx(
              "pointer-events-auto rounded-md border px-4 py-2.5 text-base shadow-md",
              t.tone === "success" && "border-green/30 bg-panel text-green",
              t.tone === "error" && "border-rust/30 bg-panel text-rust",
              t.tone === "info" && "border-line bg-ink text-white",
            )}
          >
            {t.message}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function useToast() {
  return useContext(ToastCtx);
}
