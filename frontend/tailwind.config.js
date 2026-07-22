/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          '"Inter Variable"',
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          '"Segoe UI"',
          "Roboto",
          '"Helvetica Neue"',
          "Arial",
          "sans-serif",
        ],
      },
      // Semantic type scale — use these over ad-hoc text-* sizes for headings/body.
      fontSize: {
        display: ["2rem", { lineHeight: "1.2", letterSpacing: "-0.02em", fontWeight: "600" }],
        h1: ["1.5rem", { lineHeight: "1.3", letterSpacing: "-0.02em", fontWeight: "600" }],
        h2: ["1.25rem", { lineHeight: "1.35", letterSpacing: "-0.01em", fontWeight: "600" }],
        h3: ["1.0625rem", { lineHeight: "1.45", fontWeight: "600" }],
        body: ["0.9375rem", { lineHeight: "1.6" }],
        small: ["0.8125rem", { lineHeight: "1.5" }],
        caption: ["0.75rem", { lineHeight: "1.4" }],
      },
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // Status colors — theme-aware (light uses the -600 shade, dark the -400).
        success: {
          DEFAULT: "hsl(var(--success))",
          foreground: "hsl(var(--success-foreground))",
        },
        warning: {
          DEFAULT: "hsl(var(--warning))",
          foreground: "hsl(var(--warning-foreground))",
        },
        // Brand gradient stops (indigo → violet → purple) for from-/via-/to- classes.
        brand: {
          start: "hsl(var(--brand-start))",
          mid: "hsl(var(--brand-mid))",
          end: "hsl(var(--brand-end))",
        },
      },
      // One-class brand gradients: bg-brand-gradient (diagonal, buttons/hero) and
      // bg-brand-gradient-r (horizontal, text clip / progress bars).
      backgroundImage: {
        "brand-gradient":
          "linear-gradient(to bottom right, hsl(var(--brand-start)), hsl(var(--brand-mid)))",
        "brand-gradient-r":
          "linear-gradient(to right, hsl(var(--brand-start)), hsl(var(--brand-mid)))",
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [],
}
