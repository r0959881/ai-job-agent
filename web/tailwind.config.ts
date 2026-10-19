import animate from "tailwindcss-animate";
import type { Config } from "tailwindcss";

const token = (name: string) => `hsl(var(--${name}) / <alpha-value>)`;

export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: { center: true, padding: "1.5rem", screens: { "2xl": "1280px" } },
    extend: {
      maxWidth: { content: "1280px", prose: "75ch" },
      fontFamily: { sans: ["'Inter Variable'", "Inter", "system-ui", "sans-serif"] },
      fontSize: {
        caption: ["0.75rem", { lineHeight: "1rem" }],
        body: ["0.875rem", { lineHeight: "1.375rem" }],
        section: ["1.0625rem", { lineHeight: "1.5rem", fontWeight: "600" }],
        title: ["1.5rem", { lineHeight: "2rem", fontWeight: "650", letterSpacing: "-0.01em" }],
      },
      colors: {
        border: token("border"),
        input: token("input"),
        ring: token("ring"),
        background: token("background"),
        foreground: token("foreground"),
        primary: { DEFAULT: token("primary"), foreground: token("primary-foreground") },
        secondary: { DEFAULT: token("secondary"), foreground: token("secondary-foreground") },
        muted: { DEFAULT: token("muted"), foreground: token("muted-foreground") },
        accent: { DEFAULT: token("accent"), foreground: token("accent-foreground") },
        popover: { DEFAULT: token("popover"), foreground: token("popover-foreground") },
        card: { DEFAULT: token("card"), foreground: token("card-foreground") },
        success: { DEFAULT: token("success"), foreground: token("success-foreground"), soft: token("success-soft") },
        warning: { DEFAULT: token("warning"), foreground: token("warning-foreground"), soft: token("warning-soft") },
        danger: { DEFAULT: token("danger"), foreground: token("danger-foreground"), soft: token("danger-soft") },
        info: { DEFAULT: token("info"), foreground: token("info-foreground"), soft: token("info-soft") },
        sidebar: { DEFAULT: token("sidebar"), foreground: token("sidebar-foreground") },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      boxShadow: {
        card: "var(--shadow-card)",
        overlay: "var(--shadow-overlay)",
      },
      transitionDuration: { DEFAULT: "150ms" },
      keyframes: {
        "accordion-down": { from: { height: "0" }, to: { height: "var(--radix-accordion-content-height)" } },
        "accordion-up": { from: { height: "var(--radix-accordion-content-height)" }, to: { height: "0" } },
      },
    },
  },
  plugins: [animate],
} satisfies Config;
