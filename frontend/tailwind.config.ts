import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/app/**/*.{ts,tsx}",
    "./src/components/**/*.{ts,tsx}",
    "./src/lib/**/*.{ts,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        gb: {
          bg: "#0F1115",
          card: "#1E2A38",
          border: "#2A3544",
          accent: "#FF6600",
          "accent-hover": "#E65C00",
          "text-primary": "#FFFFFF",
          "text-secondary": "#AAB2BD",
          success: "#2ECC71",
          warning: "#F39C12",
          error: "#E74C3C",
          sidebar: "#0A0D10",
        },
      },
      fontFamily: {
        heading: ["var(--font-heading)", "sans-serif"],
        body: ["var(--font-body)", "sans-serif"],
        mono: ["var(--font-mono)", "monospace"],
      },
      borderRadius: {
        gb: "8px",
      },
    },
  },
  plugins: [],
};

export default config;
