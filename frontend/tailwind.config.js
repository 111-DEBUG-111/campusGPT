/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      colors: {
        // Dark theme palette
        'bg-base': '#0a0b0f',
        'bg-surface': '#111318',
        'bg-card': '#1a1d25',
        'bg-elevated': '#1f2330',
        'border': '#2a2d3a',
        'border-light': '#353847',

        // Brand
        'brand': '#6366f1',
        'brand-light': '#818cf8',
        'brand-dark': '#4f46e5',

        // Accent
        'accent': '#06b6d4',
        'accent-light': '#22d3ee',

        // Text
        'text-primary': '#f1f5f9',
        'text-secondary': '#94a3b8',
        'text-muted': '#475569',

        // Status
        'success': '#10b981',
        'warning': '#f59e0b',
        'error': '#ef4444',
        'info': '#3b82f6',

        // Category colors
        'cat-academics': '#6366f1',
        'cat-placements': '#10b981',
        'cat-hostel': '#f59e0b',
        'cat-clubs': '#ec4899',
        'cat-policies': '#ef4444',
        'cat-faq': '#06b6d4',
        'cat-internships': '#8b5cf6',
        'cat-general': '#64748b',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'slide-up': 'slideUp 0.3s ease-out',
        'fade-in': 'fadeIn 0.2s ease-out',
        'shimmer': 'shimmer 2s linear infinite',
        'bounce-dot': 'bounceDot 1.4s infinite ease-in-out',
      },
      keyframes: {
        slideUp: {
          '0%': { transform: 'translateY(10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        bounceDot: {
          '0%, 80%, 100%': { transform: 'scale(0)', opacity: '0.3' },
          '40%': { transform: 'scale(1)', opacity: '1' },
        },
      },
      backdropBlur: {
        xs: '2px',
      },
    },
  },
  plugins: [],
}
