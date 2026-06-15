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
          user: "#F1F3F4",
          "d-bg": "#191919",
          "d-sidebar": "#212121",
          "d-border": "#333333",
          "d-text": "#E8E8E3",
          "d-muted": "#9CA3AF",
          "d-user": "#2A2A2A",
          "d-card": "#252525",
          "d-hover": "#2E2E2E",
        },
      },
      fontFamily: {
        sans: [
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
        input: "0 1px 2px rgba(16, 24, 40, 0.06), 0 0 0 1px rgba(16, 24, 40, 0.04)",
        em: "0 1px 3px rgba(16, 24, 40, 0.08), 0 0 0 1px rgba(16, 24, 40, 0.06)",
      },
    },
  },
  plugins: [],
};
