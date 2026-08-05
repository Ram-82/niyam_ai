import type { Config } from "tailwindcss";

/**
 * Tailwind theme extended FROM ``lib/tokens.css``.
 *
 * Utilities like ``bg-paper``, ``text-ink``, ``border-rule``, ``text-xs``
 * … all resolve through the CSS custom properties so the source of truth
 * stays in one file. If you find yourself reaching for a bg-slate-* or
 * text-neutral-*, stop — add a semantic token instead.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    // Reset colours entirely so nobody accidentally uses bg-blue-500.
    colors: {
      transparent: "transparent",
      current: "currentColor",
      inherit: "inherit",
      paper: "var(--paper)",
      "paper-raised": "var(--paper-raised)",
      ink: "var(--ink)",
      "ink-muted": "var(--ink-muted)",
      rule: "var(--rule)",
      "rule-strong": "var(--rule-strong)",
      accent: "var(--accent)",
      "accent-hover": "var(--accent-hover)",
      "accent-tint": "var(--accent-tint)",
      "amber-fg": "var(--amber-fg)",
      "amber-bg": "var(--amber-bg)",
      "amber-strong": "var(--amber-strong)",
      "red-fg": "var(--red-fg)",
      "red-bg": "var(--red-bg)",
      "red-strong": "var(--red-strong)",
      "green-fg": "var(--green-fg)",
      "green-bg": "var(--green-bg)",
      "green-strong": "var(--green-strong)",
      "grey-fg": "var(--grey-fg)",
      "grey-bg": "var(--grey-bg)",
      white: "#FFFFFF",
    },
    fontSize: {
      xs: ["var(--text-xs)", { lineHeight: "var(--line-height-normal)" }],
      sm: ["var(--text-sm)", { lineHeight: "var(--line-height-normal)" }],
      base: ["var(--text-base)", { lineHeight: "var(--line-height-normal)" }],
      lg: ["var(--text-lg)", { lineHeight: "var(--line-height-tight)" }],
      xl: ["var(--text-xl)", { lineHeight: "var(--line-height-tight)" }],
      display: ["var(--text-display)", { lineHeight: "1.15" }],
      score: ["var(--text-score)", { lineHeight: "1" }],
    },
    fontWeight: {
      normal: "var(--weight-normal)",
      semibold: "var(--weight-semibold)",
    },
    borderRadius: {
      none: "0",
      sm: "var(--radius-sm)",
      md: "var(--radius-md)",
      lg: "var(--radius-lg)",
      full: "9999px",
    },
    extend: {
      fontFamily: {
        // Three font roles, wired via next/font in app/layout.tsx.
        //   sans  — Inter (body, labels, controls)
        //   serif — Source Serif 4 (page titles, hero labels — Claude feel)
        //   mono  — IBM Plex Mono (money, scores, GSTINs, dates)
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        serif: ["var(--font-serif)", "Georgia", "serif"],
        mono: [
          "var(--font-mono)",
          "ui-monospace",
          "SFMono-Regular",
          "monospace",
        ],
      },
      transitionDuration: {
        fast: "var(--motion-fast)",
        base: "var(--motion-base)",
      },
      transitionTimingFunction: {
        DEFAULT: "var(--easing)",
      },
    },
  },
  plugins: [],
};
export default config;
