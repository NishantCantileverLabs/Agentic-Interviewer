"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Nav from "../../../components/Nav";
import "../../admin.css";

import { API, authFetch } from "../../../lib/auth";

/** Decision brief, embedded in-app. Polls until the async evaluation
 * pipeline has produced it (a completed session takes ~2 minutes). */
export default function BriefPage() {
  const { id } = useParams<{ id: string }>();
  const [ready, setReady] = useState<boolean | null>(null);
  const [html, setHtml] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        // brief.html is auth-gated; iframes can't carry the bearer token,
        // so fetch with auth and render via srcDoc
        const r = await authFetch(`${API}/sessions/${id}/brief.html`);
        if (!cancelled && r.ok) {
          setHtml(await r.text());
          return setReady(true);
        }
      } catch {
        /* retry */
      }
      if (!cancelled) setReady(false);
    };
    check();
    const t = setInterval(check, 8000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [id]);

  return (
    <>
      <Nav />
      <div className="frame-wrap">
        {ready ? (
          <iframe srcDoc={html} title="Decision brief" />
        ) : (
          <div className="frame-pending">
            <h2>{ready === null ? "Loading…" : "Evaluation in progress"}</h2>
            <p>
              The async pipeline scores the session after it completes (usually ~2 minutes).
              This page refreshes automatically.
            </p>
          </div>
        )}
      </div>
    </>
  );
}
