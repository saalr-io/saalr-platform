import { writeFileSync } from 'node:fs'
import { buildSitemap } from '../src/seo-build/sitemap'
import { buildLlmsTxt } from '../src/seo-build/llms'
import { EXPLAINERS } from '../src/seo/content/strategies'

const SITE = process.env.SITE_ORIGIN ?? 'https://saalr.com'
const pages = [
  { url: '/', title: 'Saalr', description: 'Research-grade options analytics for retail traders.' },
  { url: '/learn', title: 'Learn options strategies', description: 'Explainers for common options strategies.' },
  ...EXPLAINERS.map((e) => ({ url: `/learn/${e.slug}`, title: e.title, description: e.summary })),
]
writeFileSync('dist/client/sitemap.xml', buildSitemap(SITE, pages.map((p) => p.url)))
writeFileSync('dist/client/llms.txt', buildLlmsTxt(SITE, 'Saalr', 'Research-grade options analytics for retail traders.', pages))
console.log(`wrote sitemap.xml + llms.txt (${pages.length} pages)`)
