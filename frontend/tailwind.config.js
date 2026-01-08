/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        redline: {
          deleted: '#fecaca',
          'deleted-text': '#991b1b',
          inserted: '#bbf7d0',
          'inserted-text': '#166534',
        },
      },
    },
  },
  plugins: [],
}
