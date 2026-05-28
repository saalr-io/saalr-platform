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
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['ui-monospace', 'JetBrains Mono', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
} satisfies Config