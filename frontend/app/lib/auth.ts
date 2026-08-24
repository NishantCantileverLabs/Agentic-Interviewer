"use client";

/** Client-side session: JWT in localStorage, attached to every API call.
 * The backend is the enforcement point (require_role); this is just plumbing
 * plus enough state to route users to the right surface. */

import { useEffect, useState } from "react";

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const TOKEN_KEY = "session_token";

export interface AuthUser {
  id: string;
  email: string;
  name: string | null;
  account_type: "staff" | "candidate";
  role: string;
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function logout(): void {
  window.localStorage.removeItem(TOKEN_KEY);
  window.location.assign("/login");
}

export function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** fetch with the session token attached (merges with provided headers). */
export function authFetch(input: string, init?: RequestInit): Promise<Response> {
  return fetch(input, {
    ...init,
    headers: { ...authHeaders(), ...(init?.headers ?? {}) },
  });
}

/** Resolve the logged-in user (null = not logged in). `loading` guards
 * redirect flicker. */
export function useUser(): { user: AuthUser | null; loading: boolean } {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setLoading(false);
      return;
    }
    fetch(`${API}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (r) => {
        if (r.ok) setUser((await r.json()) as AuthUser);
        else window.localStorage.removeItem(TOKEN_KEY);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return { user, loading };
}

export function homeFor(user: AuthUser): string {
  // role-based landing: candidates on their interview home, staff in the console
  return user.account_type === "candidate" ? "/portal" : "/dashboard";
}
