"use client";

import { useEffect, useState } from "react";
import { authFetch } from "../../lib/auth";

/** Renders an auth-gated HTML document (brief.html, calibration.html) inside
 * an iframe. Plain <iframe src> cannot carry the bearer token, so the HTML is
 * fetched with auth and rendered via srcDoc. */
export function AuthFrame({
  url,
  title,
  className,
  pendingText = "Not ready yet — this fills in when the document is generated.",
}: {
  url: string;
  title: string;
  className?: string;
  pendingText?: string;
}) {
  const [html, setHtml] = useState<string | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "pending" | "denied">("loading");

  useEffect(() => {
    let alive = true;
    authFetch(url)
      .then(async (r) => {
        if (!alive) return;
        if (r.ok) {
          setHtml(await r.text());
          setState("ready");
        } else if (r.status === 401 || r.status === 403) {
          setState("denied");
        } else {
          setState("pending");
        }
      })
      .catch(() => alive && setState("pending"));
    return () => {
      alive = false;
    };
  }, [url]);

  if (state === "loading") {
    return (
      <div className={className} aria-busy="true">
        <div className="flex h-full items-center justify-center rounded-lg border border-line bg-panel text-sm text-muted">
          Loading the document…
        </div>
      </div>
    );
  }
  if (state === "denied") {
    return (
      <div className={className}>
        <div className="flex h-full items-center justify-center rounded-lg border border-line bg-panel p-4 text-center text-sm text-muted">
          Your account does not have access to this document — log in with an org
          account.
        </div>
      </div>
    );
  }
  if (state === "pending") {
    return (
      <div className={className}>
        <div className="flex h-full items-center justify-center rounded-lg border border-line bg-panel p-4 text-center text-sm text-muted">
          {pendingText}
        </div>
      </div>
    );
  }
  return <iframe title={title} srcDoc={html ?? ""} className={className} />;
}
