/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#6C3FC5",
          dark: "#4B238C",
          light: "#F3EEFC",
        },
        brand: {
          purple: "#6C3FC5",
          darkPurple: "#4B238C",
          lightPurple: "#F3EEFC",
          charcoal: "#171717",
          muted: "#666666",
          border: "#EAEAEA",
        }
      },
      fontFamily: {
        sans: ["'DM Sans'", "-apple-system", "BlinkMacSystemFont", "'Segoe UI'", "Roboto", "sans-serif"],
        serif: ["'Playfair Display'", "Georgia", "serif"],
        display: ["'Playfair Display'", "Georgia", "serif"],
      },
    },
  },
  plugins: [],
}
