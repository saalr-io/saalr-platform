/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import vike from 'vike/plugin'

const SITE_ORIGIN =
  (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env
    ?.SITE_ORIGIN ?? 'https://saalr.com'

export default defineConfig({
  // Inlined at build so canonical/OG/JSON-LD (origin.ts) and the build-time
  // sitemap/llms (gen-seo.ts, which reads process.env.SITE_ORIGIN) share one origin.
  define: {
    __SITE_ORIGIN__: JSON.stringify(SITE_ORIGIN),
  },
  plugins: [react(), vike()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: true,
  },
})