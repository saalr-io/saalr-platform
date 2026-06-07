// Canonical origin for absolute URLs in JSON-LD / OG / canonical tags.
// Inlined at build via the vite `define` (defaults to https://saalr.com, override
// with SITE_ORIGIN) so pages, sitemap.xml, and llms.txt all agree.
declare const __SITE_ORIGIN__: string
export const ORIGIN = __SITE_ORIGIN__
