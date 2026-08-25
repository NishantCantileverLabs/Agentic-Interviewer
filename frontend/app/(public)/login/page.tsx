"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button, Input } from "../../../components/ui";
import { cx } from "../../../lib/cx";
import { API, type AuthUser, setToken } from "../../../lib/auth";

const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID ?? "";

type Mode = "login" | "signup" | "otp";
type AccountType = "candidate" | "staff";

interface AuthResponse {
  token: string;
  user: AuthUser;
}

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (cfg: {
            client_id: string;
            callback: (resp: { credential: string }) => void;
          }) => void;
          renderButton: (el: HTMLElement, cfg: Record<string, unknown>) => void;
        };
      };
    };
  }
}

/** Role decides the destination: recruiters land in the console, candidates
 * on their interview home. */
function destinationFor(user: AuthUser): string {
  return user.account_type === "candidate" ? "/portal" : "/dashboard";
}

export default function LoginPage() {
  const [mode, setMode] = useState<Mode>("login");
  const [accountType, setAccountType] = useState<AccountType>("candidate");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [devOtp, setDevOtp] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const googleRef = useRef<HTMLDivElement>(null);

  const finish = useCallback((data: AuthResponse) => {
    setToken(data.token);
    window.location.assign(destinationFor(data.user));
  }, []);

  const post = useCallback(async (path: string, body: unknown): Promise<Response> => {
    return fetch(`${API}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }, []);

  useEffect(() => {
    if (!GOOGLE_CLIENT_ID) return;
    const render = () => {
      if (!window.google || !googleRef.current) return;
      window.google.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: async (resp) => {
          setError(null);
          const r = await post("/auth/google", {
            credential: resp.credential,
            account_type: accountType,
          });
          if (r.ok) finish((await r.json()) as AuthResponse);
          else setError(await r.text());
        },
      });
      window.google.accounts.id.renderButton(googleRef.current, {
        theme: "outline",
        shape: "rectangular",
        width: 320,
        text: mode === "signup" ? "signup_with" : "signin_with",
      });
    };
    if (window.google) {
      render();
      return;
    }
    const s = document.createElement("script");
    s.src = "https://accounts.google.com/gsi/client";
    s.async = true;
    s.onload = render;
    document.head.appendChild(s);
  }, [accountType, mode, post, finish]);

  const submit = async () => {
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") {
        const r = await post("/auth/login", { email, password });
        if (!r.ok) throw new Error(await parseDetail(r));
        finish((await r.json()) as AuthResponse);
      } else if (mode === "signup") {
        const r = await post("/auth/register", {
          name,
          email,
          password,
          account_type: accountType,
        });
        if (!r.ok) throw new Error(await parseDetail(r));
        const data = (await r.json()) as { otp_sent: boolean; dev_otp: string | null };
        setDevOtp(data.dev_otp);
        setMode("otp");
      } else {
        const r = await post("/auth/verify", { email, otp });
        if (!r.ok) throw new Error(await parseDetail(r));
        finish((await r.json()) as AuthResponse);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onEnter = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") void submit();
  };

  return (
    <div className="flex min-h-screen bg-paper">
      {/* left: brand + what awaits, per role (hidden on small screens) */}
      <aside className="hidden w-[42%] flex-col justify-between border-r border-line bg-panel p-8 lg:flex">
        <Link href="/" className="flex items-center gap-2.5 font-display text-md font-semibold text-ink">
          <span aria-hidden className="h-5 w-5 rounded-sm bg-accent" />
          AI Interview
        </Link>
        <div>
          <p className="font-mono text-xs uppercase tracking-widest text-accent">
            One login, two rooms
          </p>
          <ol className="mt-4 flex flex-col gap-5 border-l border-line pl-5">
            <li className="relative">
              <span aria-hidden className="absolute -left-[23px] top-1.5 h-2 w-2 rounded-full bg-accent" />
              <div className="font-display text-md font-semibold text-ink">Recruiters</div>
              <p className="mt-0.5 text-sm leading-relaxed text-muted">
                Your hiring console.
              </p>
            </li>
            <li className="relative">
              <span aria-hidden className="absolute -left-[23px] top-1.5 h-2 w-2 rounded-full bg-ink" />
              <div className="font-display text-md font-semibold text-ink">Candidates</div>
              <p className="mt-0.5 text-sm leading-relaxed text-muted">
                Your interviews, one press to join.
              </p>
            </li>
          </ol>
        </div>
        <p className="font-mono text-xs text-muted">a human reviews every assessment</p>
      </aside>

      {/* right: the form */}
      <main className="flex flex-1 items-center justify-center px-4 py-10">
        <div className="w-full max-w-[400px]">
          <Link href="/" className="mb-6 flex items-center gap-2.5 font-display text-md font-semibold text-ink lg:hidden">
            <span aria-hidden className="h-5 w-5 rounded-sm bg-accent" />
            AI Interview
          </Link>

          <h1 className="font-display text-xl font-semibold text-ink">
            {mode === "otp"
              ? "Check your email"
              : mode === "login"
                ? "Welcome back"
                : "Create your account"}
          </h1>
          {mode !== "otp" && (
            <p className="mt-1 text-base text-muted">
              {mode === "login" ? "Good to see you again." : "Takes under a minute."}
            </p>
          )}

          {mode !== "otp" && (
            <div className="mt-5 flex rounded-md border border-line bg-panel p-1" role="tablist">
              {(["login", "signup"] as const).map((m) => (
                <button
                  key={m}
                  role="tab"
                  aria-selected={mode === m}
                  onClick={() => setMode(m)}
                  className={cx(
                    "h-9 flex-1 rounded-sm text-base font-medium transition-colors",
                    mode === m ? "bg-accent-tint text-accent" : "text-muted hover:text-ink",
                  )}
                >
                  {m === "login" ? "Log in" : "Sign up"}
                </button>
              ))}
            </div>
          )}

          <div className="mt-4 flex flex-col gap-3">
            {mode === "signup" && (
              <>
                <fieldset>
                  <legend className="mb-1.5 text-sm font-medium text-ink-soft">I am a…</legend>
                  <div className="grid grid-cols-2 gap-2">
                    {(
                      [
                        ["candidate", "Candidate", "here to interview"],
                        ["staff", "Recruiter", "invite required"],
                      ] as const
                    ).map(([value, label, sub]) => (
                      <button
                        key={value}
                        type="button"
                        aria-pressed={accountType === value}
                        onClick={() => setAccountType(value)}
                        className={cx(
                          "rounded-md border p-3 text-left transition-colors",
                          accountType === value
                            ? "border-accent bg-accent-tint"
                            : "border-line bg-panel hover:border-accent",
                        )}
                      >
                        <div className="text-base font-semibold text-ink">{label}</div>
                        <div className="text-sm text-muted">{sub}</div>
                      </button>
                    ))}
                  </div>
                </fieldset>
                <Input
                  label="Full name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  autoComplete="name"
                />
              </>
            )}

            {mode !== "otp" && (
              <>
                <Input
                  label="Email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  onKeyDown={onEnter}
                />
                <Input
                  label="Password"
                  type="password"
                  hint={mode === "signup" ? "At least 8 characters" : undefined}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete={mode === "signup" ? "new-password" : "current-password"}
                  onKeyDown={onEnter}
                />
              </>
            )}

            {mode === "otp" && (
              <>
                <p className="text-base text-ink-soft">
                  We sent a 6-digit code to <b>{email}</b>. Enter it to verify your account.
                </p>
                {devOtp && (
                  <p className="rounded-md border border-amber/40 bg-panel p-2.5 text-sm text-amber">
                    Development mode (no email provider configured). Your code is{" "}
                    <b className="font-mono">{devOtp}</b>
                  </p>
                )}
                <Input
                  label="Verification code"
                  inputMode="numeric"
                  maxLength={6}
                  className="text-center font-mono text-lg tracking-[0.4em]"
                  value={otp}
                  onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))}
                  onKeyDown={onEnter}
                />
              </>
            )}

            {error && (
              <p role="alert" className="text-sm text-rust">
                {error}
              </p>
            )}

            <Button
              onClick={submit}
              loading={busy}
              disabledReason={
                mode === "otp"
                  ? otp.length === 6
                    ? undefined
                    : "Enter the 6-digit code"
                  : email && password && (mode === "login" || name)
                    ? undefined
                    : "Fill in the fields above first"
              }
            >
              {mode === "login" ? "Log in" : mode === "signup" ? "Continue" : "Verify and continue"}
            </Button>

            {GOOGLE_CLIENT_ID && mode !== "otp" && (
              <>
                <div className="flex items-center gap-3 text-xs text-muted">
                  <span aria-hidden className="h-px flex-1 bg-line" />
                  or
                  <span aria-hidden className="h-px flex-1 bg-line" />
                </div>
                <div ref={googleRef} className="flex justify-center" />
              </>
            )}

            {mode === "otp" && (
              <button
                className="text-sm text-muted underline-offset-2 hover:text-ink hover:underline"
                onClick={() => setMode("signup")}
              >
                Wrong email? Go back
              </button>
            )}
          </div>

          <p className="mt-8 text-sm text-muted">
            Invited to interview? You don&apos;t need an account. Use the personal link
            from your invitation email.
          </p>
        </div>
      </main>
    </div>
  );
}

async function parseDetail(r: Response): Promise<string> {
  const raw = await r.text();
  try {
    return (JSON.parse(raw) as { detail?: string }).detail ?? raw;
  } catch {
    return raw;
  }
}
