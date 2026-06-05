import type { Config } from 'vike/types'

// The authenticated app is a client-only SPA (no SSR), but it IS prerendered to a static boot
// shell (dist/client/app/index.html) so it can be served from static hosting (S3/CloudFront).
// CloudFront rewrites every /app/* path to that shell; the client router takes over from there.
export default {
  ssr: false,
  prerender: true,
} satisfies Config
