export function buildSitemap(site: string, urls: string[]): string {
  const entries = urls
    .map((u) => `  <url>\n    <loc>${site}${u}</loc>\n  </url>`)
    .join('\n')
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${entries}\n</urlset>\n`
}
