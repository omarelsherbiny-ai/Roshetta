// web/tailwind.config.ts (Tailwind config: M3 Pharmacy Emerald tokens, light and dark through CSS variables)
import type { Config } from "tailwindcss";

// Every color is a CSS variable holding RGB channels (defined in src/app/globals.css for :root and .dark).
// `<alpha-value>` keeps opacity modifiers such as bg-surface/90 working.
const COLOR_TOKENS = [
  "background",
  "surface",
  "surface-bright",
  "surface-dim",
  "surface-variant",
  "surface-container-lowest",
  "surface-container-low",
  "surface-container",
  "surface-container-high",
  "surface-container-highest",
  "surface-tint",
  "on-surface",
  "on-surface-variant",
  "on-background",
  "primary",
  "on-primary",
  "primary-container",
  "on-primary-container",
  "primary-fixed",
  "primary-fixed-dim",
  "on-primary-fixed",
  "on-primary-fixed-variant",
  "secondary",
  "on-secondary",
  "secondary-container",
  "on-secondary-container",
  "secondary-fixed",
  "secondary-fixed-dim",
  "on-secondary-fixed",
  "on-secondary-fixed-variant",
  "tertiary",
  "on-tertiary",
  "tertiary-container",
  "on-tertiary-container",
  "tertiary-fixed",
  "tertiary-fixed-dim",
  "on-tertiary-fixed",
  "on-tertiary-fixed-variant",
  "error",
  "on-error",
  "error-container",
  "on-error-container",
  "outline",
  "outline-variant",
  "inverse-surface",
  "inverse-on-surface",
  "inverse-primary",
] as const;

const colors: Record<string, string> = {};
for (const name of COLOR_TOKENS) {
  colors[name] = `rgb(var(--color-${name}) / <alpha-value>)`;
}

const config: Config = {
  darkMode: "class",
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      // Exact Stitch / Material Design 3 color tokens (values live in globals.css)
      colors,

      // Spacing tokens
      spacing: {
        "margin-mobile":    "1rem",
        "gutter-mobile":    "0.75rem",
        "margin":           "1.25rem",
        "gutter":           "1rem",
        "touch-target-min": "3rem",
        "space-xs":         "0.25rem",
        "space-sm":         "0.5rem",
        "space-md":         "1rem",
        "space-lg":         "1.5rem",
        "space-xl":         "2rem",
      },

      // Border radius
      borderRadius: {
        DEFAULT: "0.25rem",
        lg:      "0.5rem",
        xl:      "0.75rem",
        full:    "9999px",
      },

      // Font families
      fontFamily: {
        "headline":       ['"Plus Jakarta Sans"', "sans-serif"],
        "body":           ['"Noto Sans"',         "sans-serif"],
        "arabic":         ["Tajawal",             "sans-serif"],
        "stat-numeric":   ['"Plus Jakarta Sans"', "sans-serif"],
        "headline-xl":    ['"Plus Jakarta Sans"', "sans-serif"],
        "headline-lg":    ['"Plus Jakarta Sans"', "sans-serif"],
        "headline-md":    ['"Plus Jakarta Sans"', "sans-serif"],
        "headline-sm":    ['"Plus Jakarta Sans"', "sans-serif"],
        "body-lg":        ['"Noto Sans"',         "sans-serif"],
        "body-md":        ['"Noto Sans"',         "sans-serif"],
        "body-sm":        ['"Noto Sans"',         "sans-serif"],
        "label-lg":       ['"Noto Sans"',         "sans-serif"],
        "label-md":       ['"Noto Sans"',         "sans-serif"],
        "label-sm":       ['"Noto Sans"',         "sans-serif"],
      },

      // Font sizes (matching Stitch exactly)
      fontSize: {
        "stat-numeric":     ["28px", { lineHeight: "32px", fontWeight: "800" }],
        "headline-xl":      ["32px", { lineHeight: "44px", fontWeight: "800" }],
        "headline-xl-mobile":["26px",{ lineHeight: "36px", fontWeight: "800" }],
        "headline-lg":      ["24px", { lineHeight: "34px", fontWeight: "700" }],
        "headline-md":      ["20px", { lineHeight: "28px", fontWeight: "700" }],
        "headline-sm":      ["18px", { lineHeight: "26px", fontWeight: "700" }],
        "body-lg":          ["16px", { lineHeight: "26px", fontWeight: "500" }],
        "body-md":          ["14px", { lineHeight: "22px", fontWeight: "400" }],
        "body-sm":          ["12px", { lineHeight: "18px", fontWeight: "400" }],
        "label-lg":         ["14px", { lineHeight: "20px", fontWeight: "700" }],
        "label-md":         ["12px", { lineHeight: "16px", fontWeight: "700" }],
        "label-sm":         ["11px", { lineHeight: "14px", fontWeight: "500" }],
      },
    },
  },
  plugins: [],
};

export default config;