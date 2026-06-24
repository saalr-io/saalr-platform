import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Read VITE_API_BASE_URL via a globalThis cast (matches vite.config.ts; avoids
// needing @types/node so `tsc --noEmit` stays clean when this file is in include).
const API_BASE =
  (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env
    ?.VITE_API_BASE_URL ?? 'http://localhost:8000'

// Standalone SPA build of the /app shell for the Tauri desktop app (no Vike).
// HashRouter (in main-desktop.tsx) + base './' make client routing and assets
// work under Tauri's asset protocol. PostCSS/Tailwind config is found by Vite's
// upward search from root ./desktop → apps/web/postcss.config.js (no css.postcss needed).
export default defineConfig({
  root: 'desktop',
  base: './',
  plugins: [react()],
  define: {
    __SITE_ORIGIN__: JSON.stringify('https://saalr.com'),
    'import.meta.env.VITE_API_BASE_URL': JSON.stringify(API_BASE),
  },
  build: { outDir: '../dist-desktop', emptyOutDir: true },
  server: { port: 5174, strictPort: true },
})
