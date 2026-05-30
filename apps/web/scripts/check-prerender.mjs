import { readFileSync } from 'node:fs'
const html = readFileSync('dist/client/learn/bull-call-spread/index.html', 'utf8')
const checks = [['<h1', html.includes('<h1')], ['Bull Call Spread', html.includes('Bull Call Spread')],
  ['ld+json', html.includes('application/ld+json')], ['<svg', html.includes('<svg')]]
const failed = checks.filter(([, ok]) => !ok)
if (failed.length) { console.error('prerender smoke FAILED:', failed.map(([n]) => n)); process.exit(1) }
console.log('prerender smoke OK')
