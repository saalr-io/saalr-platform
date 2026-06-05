// The /app page uses a catch-all +route, so Vike can't infer the prerender URL. Emit just the boot
// shell at /app (dist/client/app/index.html). The client-side react-router (basename="/app") and the
// CloudFront /app/* rewrite resolve every deeper path at runtime.
export function onBeforePrerenderStart() {
  return ['/app']
}
