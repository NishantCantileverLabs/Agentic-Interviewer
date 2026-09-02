"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { logout, useUser } from "../lib/auth";

/** Recruiter/admin left-rail navigation, grouped per the workflow spec.
 * The admin variant is role-gated: without a staff login it redirects to
 * /login (the API enforces roles regardless — this is just honest UI).
 * Candidate surfaces get a minimal floating top bar instead. */
const SECTIONS: { title: string; links: { href: string; label: string; ico: string }[] }[] = [
  {
    title: "Hire",
    links: [
      { href: "/admin", label: "Dashboard", ico: "▦" },
      { href: "/admin/roles", label: "Roles", ico: "🧭" },
      { href: "/admin/candidacies", label: "Candidates", ico: "👥" },
      { href: "/admin/setup", label: "New interview", ico: "＋" },
    ],
  },
  {
    title: "Content",
    links: [{ href: "/admin/questions", label: "Question bank", ico: "🗂" }],
  },
  {
    title: "Quality",
    links: [
      { href: "/admin/queue", label: "Review queue", ico: "⚖" },
      { href: "/admin/calibration", label: "Calibration", ico: "🎯" },
      { href: "/admin/latency", label: "Latency", ico: "⏱" },
    ],
  },
];

export default function Nav({ variant = "admin" }: { variant?: "admin" | "user" }) {
  const path = usePathname();
  const { user, loading } = useUser();

  useEffect(() => {
    if (variant !== "admin" || loading) return;
    if (!user) window.location.assign("/login");
    else if (user.account_type === "candidate") window.location.assign("/portal");
  }, [variant, user, loading]);

  const isActive = (href: string) =>
    href === "/admin" ? path === "/admin" : path.startsWith(href);

  if (variant === "user") {
    return (
      <nav className="topnav">
        <Link href="/" className="topnav-brand">
          <span className="brand-dot" />
          AI Interview
        </Link>
        <span style={{ marginLeft: "auto" }} className="topnav-link active">
          Candidate
        </span>
      </nav>
    );
  }

  return (
    <aside className="sidebar">
      <Link href="/" className="side-brand">
        <span className="brand-dot" />
        AI Interview
      </Link>
      {SECTIONS.map((s) => (
        <div key={s.title}>
          <div className="side-section">{s.title}</div>
          {s.links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={"side-link" + (isActive(l.href) ? " active" : "")}
            >
              <span className="ico">{l.ico}</span>
              {l.label}
            </Link>
          ))}
        </div>
      ))}
      <div className="side-foot">
        {user && (
          <div className="side-user" title={user.email}>
            <span className="ico">👤</span>
            <span className="side-user-mail">{user.email}</span>
            <button className="side-logout" onClick={logout} title="Log out">⏻</button>
          </div>
        )}
        <Link href="/portal" className="side-link">
          <span className="ico">🎙</span>
          Candidate view ↗
        </Link>
      </div>
    </aside>
  );
}
