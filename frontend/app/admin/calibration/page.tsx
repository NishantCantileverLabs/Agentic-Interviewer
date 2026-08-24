"use client";

import { useEffect, useState } from "react";
import Nav from "../../components/Nav";
import "../admin.css";
import { API, authFetch } from "../../lib/auth";

export default function CalibrationPage() {
  const [html, setHtml] = useState<string | null>(null);
  const [denied, setDenied] = useState(false);

  useEffect(() => {
    // calibration.html is auth-gated; fetch with the session token and render
    // via srcDoc (iframes can't carry bearer headers)
    authFetch(`${API}/calibration.html`)
      .then(async (r) => {
        if (r.ok) setHtml(await r.text());
        else setDenied(true);
      })
      .catch(() => setDenied(true));
  }, []);

  return (
    <>
      <Nav />
      <div className="frame-wrap">
        {html !== null ? (
          <iframe srcDoc={html} title="Calibration report" />
        ) : (
          <div className="frame-pending">
            <h2>{denied ? "Log in with an org account" : "Loading…"}</h2>
            {denied && <p>The calibration report is org-side only.</p>}
          </div>
        )}
      </div>
    </>
  );
}
