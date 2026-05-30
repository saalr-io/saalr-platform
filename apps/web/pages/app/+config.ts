import type { Config } from 'vike/types'

// The authenticated app is a client-only SPA: no SSR, not prerendered.
export default {
  ssr: false,
  prerender: false,
} satisfies Config
