import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: '#070a0f',
        panel: '#0e131b',
        panel2: '#131a24',
        line: '#1d2632',
        lineSoft: '#161d27',
        txt: '#e7ecf3',
        txtDim: '#8b95a7',
        txtFaint: '#5b6678',
        pos: '#2ee6a6',
        neg: '#ff5d73',
        warn: '#ffc24b',
        accent: '#4da3ff',
        accent2: '#9b7bff',
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
      keyframes: {
        pulse2: { '0%,100%': { opacity: '1' }, '50%': { opacity: '0.3' } },
        fadeUp: {
          '0%': { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        pulse2: 'pulse2 2s ease-in-out infinite',
        fadeUp: 'fadeUp 0.4s ease both',
      },
    },
  },
  plugins: [],
} satisfies Config
