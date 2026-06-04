import { readFileSync } from 'node:fs'
const html = readFileSync('dist/client/learn/bull-call-spread/index.html', 'utf8')
const checks = [['<h1', html.includes('<h1')], ['Bull Call Spread', html.includes('Bull Call Spread')],
  ['ld+json', html.includes('application/ld+json')], ['<svg', html.includes('<svg')]]
const failed = checks.filter(([, ok]) => !ok)
if (failed.length) { console.error('prerender smoke FAILED:', failed.map(([n]) => n)); process.exit(1) }
console.log('prerender smoke OK')

// Glossary index
const glossaryIndex = readFileSync('dist/client/glossary/index.html', 'utf8')
const glossaryIndexChecks = [['DefinedTermSet', glossaryIndex.includes('DefinedTermSet')]]
const failedGlossaryIndex = glossaryIndexChecks.filter(([, ok]) => !ok)
if (failedGlossaryIndex.length) { console.error('glossary index prerender FAILED:', failedGlossaryIndex.map(([n]) => n)); process.exit(1) }
console.log('glossary index OK')

// Theta term page
const thetaHtml = readFileSync('dist/client/glossary/theta/index.html', 'utf8')
const thetaChecks = [
  ['Theta', thetaHtml.includes('Theta')],
  ['application/ld+json', thetaHtml.includes('application/ld+json')],
  ['SpeakableSpecification', thetaHtml.includes('SpeakableSpecification')],
  ['geo-speakable', thetaHtml.includes('geo-speakable')],
  ['sameAs', thetaHtml.includes('"sameAs"')],
]
const failedTheta = thetaChecks.filter(([, ok]) => !ok)
if (failedTheta.length) { console.error('theta page prerender FAILED:', failedTheta.map(([n]) => n)); process.exit(1) }
console.log('theta page OK')

// llms-full.txt
const llmsFull = readFileSync('dist/client/llms-full.txt', 'utf8')
const llmsFullChecks = [
  ['Theta (glossary term)', llmsFull.includes('Theta')],
  ['Bull Call Spread (explainer)', llmsFull.includes('Bull Call Spread')],
]
const failedLlmsFull = llmsFullChecks.filter(([, ok]) => !ok)
if (failedLlmsFull.length) { console.error('llms-full.txt FAILED:', failedLlmsFull.map(([n]) => n)); process.exit(1) }
console.log('llms-full.txt OK')

// Pro-leak guard: the Pro iron-condor academy lesson body must NOT appear in llms-full.txt.
const PRO_SENTINEL = 'An **iron condor** combines a short out-of-the-money call spread'
const ironCondorMd = readFileSync('../../packages/content/saalr_content/modules/60-iron-condor-construction.md', 'utf8')
if (!ironCondorMd.includes(PRO_SENTINEL)) {
  console.error('Pro-leak guard FAILED: sentinel phrase no longer in the iron-condor lesson — update PRO_SENTINEL'); process.exit(1)
}
if (llmsFull.includes(PRO_SENTINEL)) {
  console.error('Pro-leak guard FAILED: iron-condor Pro lesson body leaked into llms-full.txt'); process.exit(1)
}
console.log('Pro-leak guard OK')

// sitemap.xml and llms.txt include /glossary/theta
const sitemap = readFileSync('dist/client/sitemap.xml', 'utf8')
const llmsTxt = readFileSync('dist/client/llms.txt', 'utf8')
const sitemapChecks = [['/glossary/theta in sitemap.xml', sitemap.includes('/glossary/theta')]]
const llmsTxtChecks = [['/glossary/theta in llms.txt', llmsTxt.includes('/glossary/theta')]]
const failedSitemap = sitemapChecks.filter(([, ok]) => !ok)
const failedLlmsTxt = llmsTxtChecks.filter(([, ok]) => !ok)
if (failedSitemap.length) { console.error('sitemap.xml FAILED:', failedSitemap.map(([n]) => n)); process.exit(1) }
if (failedLlmsTxt.length) { console.error('llms.txt FAILED:', failedLlmsTxt.map(([n]) => n)); process.exit(1) }
console.log('sitemap.xml + llms.txt OK')
