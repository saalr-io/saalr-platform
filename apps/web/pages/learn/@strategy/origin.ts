// Canonical origin used for absolute URLs in JSON-LD / OG / canonical tags.
// Inlined at build via the vite `define` (defaults to https://saalr.com, override
// with the SITE_ORIGIN env var) so pages, sitemap.xml, and llms.txt agree.
declare const __SITE_ORIGIN__: string
export const ORIGIN = __SITE_ORIGIN__
