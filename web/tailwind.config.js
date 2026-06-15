/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        em: {
          bg: "#FBFBFA",
          sidebar: "#F3F3EF",
          border: "#E8E8E3",
          text: "#13343B",
          muted: "#6B7280",
          accent: "#20808D",
          "accent-hover": "#1A6A75",
          "accent-soft": "#E6F4F5",
          user: "#F4F4F4",
          "d-bg": "#212121",
          "d-sidebar": "#171717",
          "d-border": "#ffffff14",
          "d-text": "#ECECEC",
          "d-muted": "#A0A0A0",
          "d-user": "#303030",
          "d-card": "#2f2f2f",
          "d-hover": "#ffffff0a",
          "d-accent-soft": "#1A3338",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
      boxShadow: {
        input:
          "0 1px 2px rgba(16, 24, 40, 0.06), 0 0 0 1px rgba(16, 24, 40, 0.04)",
        em: "0 1px 3px rgba(16, 24, 40, 0.08), 0 0 0 1px rgba(16, 24, 40, 0.06)",
        glow: "0 0 0 4px rgba(32, 128, 141, 0.12)",
        "glow-lg": "0 0 40px -8px rgba(32, 128, 141, 0.35)",
        float: "0 8px 30px -6px rgba(16, 24, 40, 0.12)",
        "float-dark": "0 8px 30px -6px rgba(0, 0, 0, 0.45)",
      },
      borderRadius: {
        "2.5xl": "1.25rem",
        "3xl": "1.5rem",
      },
      transitionTimingFunction: {
        spring: "cubic-bezier(0.34, 1.56, 0.64, 1)",
        smooth: "cubic-bezier(0.4, 0, 0.2, 1)",
        out: "cubic-bezier(0, 0, 0.2, 1)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        "slide-in-right": {
          "0%": { opacity: "0", transform: "translateX(12px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        "slide-in-left": {
          "0%": { opacity: "0", transform: "translateX(-12px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        "slide-panel": {
          "0%": { transform: "translateX(100%)" },
          "100%": { transform: "translateX(0)" },
        },
        "scale-in": {
          "0%": { opacity: "0", transform: "scale(0.95)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        "pulse-soft": {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.85", transform: "scale(0.98)" },
        },
        "logo-glow": {
          "0%, 100%": { boxShadow: "0 0 0 0 rgba(32, 128, 141, 0.25)" },
          "50%": { boxShadow: "0 0 24px 4px rgba(32, 128, 141, 0.2)" },
        },
        "pulse-dot": {
          "0%, 80%, 100%": { opacity: "0.25", transform: "scale(0.75)" },
          "40%": { opacity: "1", transform: "scale(1)" },
        },
        "blink-cursor": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.45s smooth both",
        "fade-in": "fade-in 0.3s smooth both",
        "slide-in-right": "slide-in-right 0.4s smooth both",
        "slide-in-left": "slide-in-left 0.4s smooth both",
        "slide-panel": "slide-panel 0.35s smooth both",
        "scale-in": "scale-in 0.35s spring both",
        shimmer: "shimmer 2.5s linear infinite",
        "pulse-soft": "pulse-soft 2.5s ease-in-out infinite",
        "logo-glow": "logo-glow 3s ease-in-out infinite",
        "pulse-dot": "pulse-dot 1.4s infinite ease-in-out both",
        "blink-cursor": "blink-cursor 1s step-end infinite",
      },
    },
  },
  plugins: [],
};
