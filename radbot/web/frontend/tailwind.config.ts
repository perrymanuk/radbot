import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        mono: ['"Source Code Pro"', "monospace"],
      },
      colors: {
        bg: {
          primary: "#0e1419",
          secondary: "#121c2b",
          tertiary: "#1b2939",
        },
        accent: {
          blue: "#3584e4",
          "blue-dark": "#2a6bbd",
        },
        txt: {
          primary: "#e2e2e2",
          secondary: "#9eacb9",
        },
        border: "#304050",
        terminal: {
          green: "#33FF33",
          amber: "#FFBF00",
          red: "#CC0000",
          blue: "#0066FF",
        },
      },
      borderRadius: {
        none: "0",
      },
      keyframes: {
        "terminal-blink": {
          "0%, 49%": { opacity: "0" },
          "50%, 100%": { opacity: "1" },
        },
        pulse: {
          "0%": { boxShadow: "0 0 5px #3584e4" },
          "50%": { boxShadow: "0 0 15px #3584e4, 0 0 30px #3584e4" },
          "100%": { boxShadow: "0 0 5px #3584e4" },
        },
        "stt-pulse": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.6" },
        },
        "pulse-blue": {
          "0%": { boxShadow: "0 0 0 0 rgba(53, 132, 228, 0.7)" },
          "70%": { boxShadow: "0 0 0 5px rgba(53, 132, 228, 0)" },
          "100%": { boxShadow: "0 0 0 0 rgba(53, 132, 228, 0)" },
        },
      },
      animation: {
        "terminal-blink": "terminal-blink 0.8s infinite",
        pulse: "pulse 2s infinite",
        "stt-pulse": "stt-pulse 1s ease-in-out infinite",
        "pulse-blue": "pulse-blue 2s infinite",
      },
    },
  },
  plugins: [],
};

export default config;
