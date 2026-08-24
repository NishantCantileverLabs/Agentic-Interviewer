"use client";

import "../styles/tokens.css";
import { useEffect } from "react";
import { AppShell, type OrgRole } from "../../components/shells/AppShell";
import { ToastProvider } from "../../components/ui";
import { logout, useUser } from "../../lib/auth";

/** Org surface gate + shell. The API enforces roles on every call; this keeps
 * the UI honest (candidates and anonymous visitors never see org chrome). */
export default function OrgLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useUser();

  useEffect(() => {
    if (loading) return;
    if (!user) window.location.assign("/login");
    else if (user.account_type === "candidate") window.location.assign("/portal");
  }, [user, loading]);

  if (loading || !user || user.account_type === "candidate") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-paper text-muted">
        Checking your access…
      </div>
    );
  }

  const role: OrgRole =
    user.role === "admin" ? "admin" : user.role === "reviewer" ? "reviewer" : "recruiter";

  return (
    <ToastProvider>
      <AppShell role={role} userEmail={user.email} onLogout={logout}>
        {children}
      </AppShell>
    </ToastProvider>
  );
}
