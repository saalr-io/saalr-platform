import { writeFileSync } from 'node:fs'
import { buildSitemap } from '../src/seo-build/sitemap'
import { buildLlmsTxt, buildLlmsFullTxt, explainerToText, glossaryTermToText } from '../src/seo-build/llms'
import { EXPLAINERS } from '../src/seo/content/strategies'
import { GLOSSARY } from '../src/seo/content/glossary'
import { ACADEMY_MODULES } from '../src/academy/modules.generated'

const ACADEMY_DESC = 'Free, plain-English lessons on options — from what an option is to how volatility is priced in.'

const SITE = process.env.SITE_ORIGIN ?? 'https://saalr.com'
const freeAcademy = ACADEMY_MODULES.filter((m) => m.body !== null)
const pages = [
  { url: '/', title: 'SAALR — Research-grade options analytics', description: 'Build and price multi-leg options strategies, study volatility, run backtests, and read multi-agent research notes — from one fast terminal.' },
  { url: '/learn', title: 'Learn options strategies', description: 'Explainers for common options strategies.' },
  ...EXPLAINERS.map((e) => ({ url: `/learn/${e.slug}`, title: e.title, description: e.summary })),
  { url: '/glossary', title: 'Options glossary', description: 'Plain-English definitions of options terms, each with examples and sources.' },
  ...GLOSSARY.map((t) => ({ url: `/glossary/${t.slug}`, title: t.term, description: t.short })),
  { url: '/academy', title: 'OptionsAcademy', description: ACADEMY_DESC },
  ...freeAcademy.map((m) => ({ url: `/academy/${m.slug}`, title: m.title, description: m.summary })),
]
writeFileSync('dist/client/sitemap.xml', buildSitemap(SITE, pages.map((p) => p.url)))
writeFileSync(
  'dist/client/llms.txt',
  buildLlmsTxt(SITE, 'Saalr', 'Research-grade options analytics for retail traders.', pages) +
    `\nSee also: ${SITE}/llms-full.txt (full content)\n`,
)

const fullSections = [
  { heading: 'Options strategies', entries: EXPLAINERS.map((e) => ({ title: e.title, url: `/learn/${e.slug}`, body: explainerToText(e) })) },
  { heading: 'OptionsAcademy', entries: freeAcademy.map((m) => ({ title: m.title, url: `/academy/${m.slug}`, body: m.body ?? '' })) },
  { heading: 'Options glossary', entries: GLOSSARY.map((t) => ({ title: t.term, url: `/glossary/${t.slug}`, body: glossaryTermToText(t) })) },
]
writeFileSync('dist/client/llms-full.txt', buildLlmsFullTxt(SITE, 'Saalr', 'Research-grade options analytics for retail traders.', fullSections))

console.log(`wrote sitemap.xml + llms.txt + llms-full.txt (${pages.length} pages)`)
