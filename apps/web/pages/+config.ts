import type { Config } from 'vike/types'
import vikeReact from 'vike-react/config'

// Global Vike config. Public pages are statically prerendered (SSG); the
// authenticated app under /app/* opts out of SSR/prerender (see app/+config.ts).
export default {
  extends: [vikeReact],
  prerender: true,
  title: 'SAALR',
  favicon: '/favicon.svg',
} satisfies Config
