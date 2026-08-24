import Link from "next/link";
import "./styles/tokens.css";
import { CONTACT_EMAIL, ORG_NAME } from "../lib/brand";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-paper px-4">
      <div className="w-full max-w-[440px] rounded-lg border border-line bg-panel p-6 text-center">
        <div className="mx-auto flex items-center justify-center gap-2.5">
          <span aria-hidden className="h-5 w-5 rounded-sm bg-accent" />
          <span className="font-display text-md font-semibold text-ink">{ORG_NAME}</span>
        </div>
        <p className="mt-5 font-mono text-xs uppercase tracking-widest text-muted">404</p>
        <h1 className="mt-1 font-display text-xl font-semibold text-ink">
          This page doesn&apos;t exist
        </h1>
        <p className="mt-2 text-base leading-relaxed text-ink-soft">
          If you followed an interview link, check it matches your invitation email
          exactly — or ask the team for a fresh one.
        </p>
        <div className="mt-5 flex items-center justify-center gap-4 text-base">
          <Link href="/" className="text-accent underline-offset-4 hover:underline">
            Go to the homepage
          </Link>
          <a
            href={`mailto:${CONTACT_EMAIL}`}
            className="text-muted underline-offset-4 hover:text-ink hover:underline"
          >
            Contact us
          </a>
        </div>
      </div>
    </div>
  );
}
