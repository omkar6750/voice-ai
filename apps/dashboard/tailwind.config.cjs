const plugin = require("tailwindcss/plugin");

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        card: "var(--card)",
        primary: "var(--primary)",
        "primary-foreground": "var(--primary-foreground)",
        secondary: "var(--secondary)",
        muted: "var(--muted)",
        "muted-foreground": "var(--muted-foreground)",
        accent: "var(--accent)",
        "accent-foreground": "var(--accent-foreground)",
        border: "var(--border)",
        input: "var(--input)",
        ring: "var(--ring)",
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [
    plugin(({ addBase }) => {
      addBase({
        ":root": {
          "--background": "#eef0f3",
          "--foreground": "#172033",
          "--card": "#f8f9fb",
          "--primary": "#315efb",
          "--primary-foreground": "#ffffff",
          "--secondary": "#e7eaf0",
          "--muted": "#e4e7ec",
          "--muted-foreground": "#687386",
          "--accent": "#e4eaff",
          "--accent-foreground": "#173185",
          "--border": "#d4d9e2",
          "--input": "#d4d9e2",
          "--ring": "#315efb",
          "--radius": "0.5rem",
        },
      });
    }),
  ],
};
