import type { Config } from "tailwindcss";

/**
 * Tokens are the source of truth for the F0-F9 build (see DESIGN.md).
 * Components use these named tokens only — no arbitrary hex or px.
 * Scoped `content` to the new platform surfaces so the legacy aurora-glass
 * pages (/interview, /admin, /portal, /candidate) keep their own CSS untouched.
 */
const config: Config = {
  content: [
    "./app/not-found.tsx",
    "./app/i/**/*.{ts,tsx}",
    "./app/(org)/**/*.{ts,tsx}",
    "./app/(public)/**/*.{ts,tsx}",
    "./app/dev/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    // Replace the default palette entirely — only tokens exist.
    colors: {
      transparent: "transparent",
      current: "currentColor",
      ink: { DEFAULT: "#181b1f", soft: "#3a4048" },
      paper: "#f7f6f2",
      panel: "#ffffff",
      line: "#d9d6cd",
      muted: "#6a7078",
      accent: { DEFAULT: "#0b6b70", tint: "#e5f0f0", strong: "#085055" },
      // status hues (paired with label + glyph in StatusChip, never color-alone)
      slate: "#697079",
      info: "#2f5fa6",
      amber: "#9a6b0c",
      green: "#2f7350",
      violet: "#6b4a9c",
      rust: "#a93f2c",
      white: "#ffffff",
      black: "#000000",
    },
    borderRadius: {
      none: "0",
      sm: "4px",
      md: "6px",
      lg: "10px",
      xl: "14px",
      full: "9999px",
    },
    // NOTE: this REPLACES Tailwind's spacing scale — any step missing here
    // emits no CSS at all and the utility silently does nothing. Half-steps
    // and the fixed element sizes below were absent, so ~33 utilities used
    // across the app (py-0.5, px-2.5, gap-1.5, h-14 nav bars, w-40 columns…)
    // were dead: chips had no padding and the sticky nav collapsed onto its
    // own border. Add a step here before using it.
    spacing: {
      0: "0",
      px: "1px",
      0.5: "2px",
      1: "4px",
      1.5: "6px",
      2: "8px",
      2.5: "10px",
      3: "12px",
      3.5: "14px",
      4: "16px",
      5: "24px",
      6: "32px",
      7: "28px",
      8: "48px",
      9: "36px",
      10: "64px",
      11: "44px", // minimum touch target (Button/ButtonLink md)
      12: "96px",
      // fixed element sizes (nav heights, column widths, scroll offsets) —
      // these follow Tailwind's default px values, not the rhythm above
      14: "56px",
      20: "80px",
      24: "96px",
      36: "144px",
      40: "160px",
      44: "176px",
      48: "192px",
      56: "224px",
      64: "256px",
      72: "288px",
    },
    fontFamily: {
      display: ['"Space Grotesk"', "system-ui", "sans-serif"],
      body: ['"Inter"', "system-ui", "sans-serif"],
      mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
    },
    fontSize: {
      xs: ["0.75rem", { lineHeight: "1rem" }],
      sm: ["0.8125rem", { lineHeight: "1.15rem" }],
      base: ["0.875rem", { lineHeight: "1.4rem" }],
      md: ["1rem", { lineHeight: "1.55rem" }],
      lg: ["1.25rem", { lineHeight: "1.6rem" }],
      xl: ["1.5rem", { lineHeight: "1.85rem" }],
      "2xl": ["2rem", { lineHeight: "2.25rem" }],
      "3xl": ["2.75rem", { lineHeight: "2.9rem" }],
    },
    boxShadow: {
      none: "none",
      sm: "0 1px 2px rgba(24,27,31,0.06)",
      md: "0 2px 8px rgba(24,27,31,0.08)",
    },
    extend: {
      keyframes: {
        "live-pulse": {
          "0%,100%": { opacity: "1" },
          "50%": { opacity: "0.35" },
        },
        "orb-ring": {
          "0%": { transform: "scale(1)", opacity: "1" },
          "100%": { transform: "scale(1.25)", opacity: "0" },
        },
      },
      animation: {
        "live-pulse": "live-pulse 1.4s ease-in-out infinite",
        "orb-ring": "orb-ring 1.6s ease-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
