import type { Config } from "tailwindcss";

/**
 * After-Hours Terminal — tokens map to CSS variables in index.css so the whole
 * system is themeable from one place and contrast stays auditable.
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        border: "var(--border)",
        text: "var(--text)",
        muted: "var(--text-muted)",
        accent: "var(--accent)",
        bull: "var(--bull)",
        bear: "var(--bear)",
        neutral: "var(--neutral)",
        info: "var(--info)",
      },
      fontFamily: {
        display: ['"Space Grotesk"', "system-ui", "sans-serif"],
        sans: ['"IBM Plex Sans"', "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
      },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      maxWidth: { content: "1440px" },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: { "fade-up": "fade-up 180ms ease-out" },
    },
  },
  plugins: [],
} satisfies Config;
