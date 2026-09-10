/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Original Rooman Billing Light Theme Palette
        brand: {
          50: 'var(--brand-50, #eff6ff)',
          100: 'var(--brand-100, #dbeafe)',
          200: 'var(--brand-200, #bfdbfe)',
          300: 'var(--brand-300, #93c5fd)',
          400: 'var(--brand-400, #60a5fa)',
          500: 'var(--brand-500, #3b82f6)',
          600: 'var(--brand-600, #2563eb)', // Primary brand accent
          700: 'var(--brand-700, #1d4ed8)',
          800: 'var(--brand-800, #1e40af)',
          900: 'var(--brand-900, #1e3a8a)',
          950: 'var(--brand-950, #172554)',
        },
        surface: {
          canvas: '#F8FAFC',  // Slate 50 app background
          card: '#FFFFFF',    // Clean card surface
          subtle: '#F1F5F9',  // Subtle component background
          hover: '#F8FAFC',   // Hover background
          border: '#E2E8F0',  // Slate 200 border
        },
        financial: {
          paid: '#059669',     // Emerald 600
          paidBg: '#ECFDF5',   // Emerald 50
          trial: '#D97706',    // Amber 600
          trialBg: '#FFFBEB',  // Amber 50
          overdue: '#DC2626',  // Rose 600
          overdueBg: '#FEF2F2',// Rose 50
          draft: '#64748B',    // Slate 500
          draftBg: '#F1F5F9',  // Slate 100
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'Courier New', 'monospace'],
      },
      boxShadow: {
        '3xs': '0 1px 1px 0 rgba(0, 0, 0, 0.03)',
        '2xs': '0 1px 2px 0 rgba(0, 0, 0, 0.04)',
        'xs': '0 1px 2px 0 rgba(0, 0, 0, 0.06)',
        'subtle': '0 1px 2px 0 rgba(0, 0, 0, 0.04)',
        'card': '0 1px 3px 0 rgba(0, 0, 0, 0.06), 0 1px 2px 0 rgba(0, 0, 0, 0.03)',
        'elevated': '0 4px 6px -1px rgba(0, 0, 0, 0.07), 0 2px 4px -1px rgba(0, 0, 0, 0.04)',
        'modal': '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
      },
      dropShadow: {
        '2xs': '0 1px 1px rgba(0, 0, 0, 0.05)',
      },
      backdropBlur: {
        xs: '2px',
      },
      keyframes: {
        'toast-in': {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'toast-in': 'toast-in 0.2s ease-out',
      },
    },
  },
  plugins: [],
}
