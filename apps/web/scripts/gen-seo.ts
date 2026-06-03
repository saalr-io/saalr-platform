import { writeFileSync } from 'node:fs'
import { buildSitemap } from '../src/seo-build/sitemap'
import { buildLlmsTxt } from '../src/seo-build/llms'
import { EXPLAINERS } from '../src/seo/content/strategies'
import { ACADEMY_MODULES } from '../src/academy/modules.generated'

const ACADEMY_DESC = 'Free, plain-English lessons on options — from what an option is to how volatility is priced in.'

const SITE = process.env.SITE_ORIGIN ?? 'https://saalr.com'
const pages = [
  { url: '/', title: 'Saalr — Research-grade options analytics', description: 'Build and price multi-leg options strategies, study volatility, run backtests, and read multi-agent research notes — from one fast terminal.' },
  { url: '/learn', title: 'Learn options strategies', description: 'Explainers for common options strategies.' },
  ...EXPLAINERS.map((e) => ({ url: `/learn/${e.slug}`, title: e.title, description: e.summary })),
  { url: '/academy', title: 'OptionsAcademy', description: ACADEMY_DESC },
  ...ACADEMY_MODULES.filter((m) => m.body !== null).map((m) => ({ url: `/academy/${m.slug}`, title: m.title, description: m.summary })),
]
writeFileSync('dist/client/sitemap.xml', buildSitemap(SITE, pages.map((p) => p.url)))
writeFileSync('dist/client/llms.txt', buildLlmsTxt(SITE, 'Saalr', 'Research-grade options analytics for retail traders.', pages))
console.log(`wrote sitemap.xml + llms.txt (${pages.length} pages)`)
