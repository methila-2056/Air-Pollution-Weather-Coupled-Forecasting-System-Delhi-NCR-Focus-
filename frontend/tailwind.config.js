/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'Noto Sans', 'Segoe UI', 'system-ui', '-apple-system', 'sans-serif'],
      },
      colors: {
        navy: {
          900: '#0a0e27',
          800: '#111640',
          700: '#1a1f52',
          600: '#252b68',
        },
        inst: {
          50: '#f0f5fa',
          100: '#dbe8f3',
          200: '#bcd5ea',
          300: '#8fb9dd',
          400: '#5a93c9',
          500: '#2f76b4',
          600: '#1d5f9c',
          700: '#0B4F8A',
          800: '#0a4172',
          900: '#0a3458',
        },
        accent: {
          blue: '#2563eb',
          cyan: '#0891b2',
          green: '#16a34a',
          amber: '#d97706',
          red: '#dc2626',
        },
      },
      boxShadow: {
        card: '0 1px 2px 0 rgb(15 23 42 / 0.05), 0 1px 3px 0 rgb(15 23 42 / 0.1)',
      },
    },
  },
  plugins: [],
}