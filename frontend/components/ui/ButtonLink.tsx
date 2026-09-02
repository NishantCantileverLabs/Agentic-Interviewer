import Link from "next/link";
import { cx } from "../../lib/cx";

type Variant = "primary" | "secondary" | "danger" | "ghost";
type Size = "sm" | "md";

const BASE =
  "inline-flex items-center justify-center gap-2 rounded-md font-body font-medium " +
  "transition-colors select-none no-underline";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-white hover:bg-accent-strong",
  secondary: "bg-panel text-ink border border-line hover:bg-paper",
  danger: "bg-rust text-white hover:opacity-90",
  ghost: "bg-transparent text-ink hover:bg-paper",
};

// md meets the 44px minimum touch target; sm (36px) is for dense org tables
const SIZES: Record<Size, string> = {
  sm: "h-9 px-3 text-sm",
  md: "h-11 px-4 text-base",
};

export interface ButtonLinkProps {
  href: string;
  variant?: Variant;
  size?: Size;
  children: React.ReactNode;
  className?: string;
}

/** A link that looks like a Button — the valid-HTML way to make a primary
 * action navigate (never nest a <button> inside an <a>). */
export function ButtonLink({ href, variant = "primary", size = "md", children, className }: ButtonLinkProps) {
  return (
    <Link href={href} className={cx(BASE, VARIANTS[variant], SIZES[size], className)}>
      {children}
    </Link>
  );
}
