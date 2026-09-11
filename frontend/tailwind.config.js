/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Target Reference Palette: Deep Navy, Indigo & Primary Blue with Pink & Soft Pastels
        brand: {
          50: 'var(--brand-50, #e8ebfc)',
          100: 'var(--brand-100, #e9e8fa)',
          200: 'var(--brand-200, #d0d7f9)',
          300: 'var(--brand-300, #a7b5f2)',
          400: 'var(--brand-400, #6b7ee3)',
          500: 'var(--brand-500, #3f51c9)',
          600: 'var(--brand-600, #25247a)',
          700: 'var(--brand-700, #1f1e6b)',
          800: 'var(--brand-800, #171b63)',
          900: 'var(--brand-900, #11194f)',
          950: 'var(--brand-950, #0b0f33)',
        },
        surface: {
          canvas: 'var(--page-bg, #F7F8FC)',
          card: 'var(--card-bg, #FFFFFF)',
          subtle: 'var(--accent-lavender, #E9E8FA)',
          hover: 'var(--accent-soft-blue, #E8EBFC)',
          border: 'var(--border-color, #E7E9F2)',
        },
        accent: {
          pink: '#E83E8C',
          softPink: '#F9D9E8',
          lavender: '#E9E8FA',
          softBlue: '#E8EBFC',
          mint: '#DDF4EA',
          peach: '#FCEBD9',
        },
        navy: {
          950: '#0B0F33',
          900: '#11194F',
          800: '#171B63',
          700: '#25247A',
          600: '#3F51C9',
        },
        emerald: {
          50: '#DDF4EA',
          200: '#BCEBD6',
          500: '#107548',
          600: '#107548',
          700: '#0E623D',
        },
        rose: {
          50: '#F9D9E8',
          200: '#F3B8D4',
          500: '#D81B60',
          600: '#D81B60',
          700: '#B71550',
        },
        amber: {
          50: '#FCEBD9',
          200: '#F7D7B5',
          500: '#C05621',
          600: '#C05621',
          700: '#9C4215',
        },
        sky: {
          50: '#E8EBFC',
          200: '#D0D7F9',
          500: '#3F51C9',
          600: '#3F51C9',
          700: '#25247A',
        },
        financial: {
          paid: '#107548',
          paidBg: '#DDF4EA',
          trial: '#C05621',
          trialBg: '#FCEBD9',
          overdue: '#D81B60',
          overdueBg: '#F9D9E8',
          draft: '#59617D',
          draftBg: '#E9E8FA',
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
