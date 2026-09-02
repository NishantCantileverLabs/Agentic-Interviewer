"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cx } from "../../lib/cx";

export type OrgRole = "admin" | "recruiter" | "reviewer";

interface NavItem {
  href: string;
  label: string;
  /** minimum role that sees this item; reviewer < recruiter < admin */
  minRole: OrgRole;
}

const RANK: Record<OrgRole, number> = { reviewer: 1, recruiter: 2, admin: 3 };

const NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", minRole: "recruiter" },
  { href: "/roles", label: "Roles", minRole: "recruiter" },
  { href: "/candidates", label: "Candidates", minRole: "reviewer" },
  { href: "/questions", label: "Questions", minRole: "recruiter" },
  { href: "/review", label: "Review queue", minRole: "reviewer" },
  { href: "/analytics", label: "Analytics", minRole: "reviewer" },
  { href: "/settings", label: "Settings", minRole: "admin" },
];

export interface AppShellProps {
  children: React.ReactNode;
  role: OrgRole;
  userEmail?: string;
  orgName?: string;
  /** breadcrumb trail after the section, e.g. ["Candidates", "Priya S."] */
  breadcrumbs?: { label: string; href?: string }[];
  onLogout?: () => void;
}

/** The org surface: dense, information-first, keyboard-friendly. Left nav is
 * role-filtered per §1; breadcrumbs in the top bar. */
export function AppShell({
  children,
  role,
  userEmail,
  orgName = "AI Interview",
  breadcrumbs,
  onLogout,
}: AppShellProps) {
  const path = usePathname();
  const items = NAV.filter((n) => RANK[role] >= RANK[n.minRole]);

  return (
    <div className="flex min-h-screen bg-paper">
      <aside className="fixed inset-y-0 left-0 z-40 flex w-[220px] flex-col border-r border-line bg-panel">
        <Link href="/dashboard" className="flex items-center gap-2.5 border-b border-line px-4 py-4">
          <span aria-hidden className="h-5 w-5 rounded-sm bg-accent" />
          <span className="font-display text-base font-semibold text-ink">{orgName}</span>
        </Link>
        <nav aria-label="Main" className="flex-1 overflow-y-auto p-2">
          {items.map((n) => {
            const active = path === n.href || path.startsWith(n.href + "/");
            return (
              <Link
                key={n.href}
                href={n.href}
                aria-current={active ? "page" : undefined}
                className={cx(
                  "block rounded-md px-3 py-2 text-base font-medium transition-colors",
                  active ? "bg-accent-tint text-accent" : "text-ink-soft hover:bg-paper",
                )}
              >
                {n.label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-line p-3">
          {userEmail && (
            <div className="mb-2 truncate font-mono text-xs text-muted" title={userEmail}>
              {userEmail}
            </div>
          )}
          {onLogout && (
            <button
              onClick={onLogout}
              className="w-full rounded-md border border-line px-3 py-1.5 text-sm text-ink-soft hover:bg-paper"
            >
              Log out
            </button>
          )}
        </div>
      </aside>

      <div className="ml-[220px] flex min-h-screen flex-1 flex-col max-[900px]:ml-0">
        {breadcrumbs && breadcrumbs.length > 0 && (
          <header className="border-b border-line bg-panel px-6 py-3">
            <nav aria-label="Breadcrumb" className="flex items-center gap-2 text-sm text-muted">
              {breadcrumbs.map((b, i) => (
                <span key={i} className="flex items-center gap-2">
                  {i > 0 && <span aria-hidden>/</span>}
                  {b.href ? (
                    <Link href={b.href} className="hover:text-ink">
                      {b.label}
                    </Link>
                  ) : (
                    <span className="text-ink">{b.label}</span>
                  )}
                </span>
              ))}
            </nav>
          </header>
        )}
        <main className="flex-1 px-6 py-5">{children}</main>
      </div>
    </div>
  );
}
