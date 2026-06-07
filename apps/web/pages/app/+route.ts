import type { PageContext } from 'vike/types'

// Catch-all: this page owns /app and everything under it. Client-side
// react-router (with basename="/app") then handles the sub-routes.
export default function route(pageContext: PageContext): boolean {
  const url = pageContext.urlPathname
  return url === '/app' || url.startsWith('/app/')
}
