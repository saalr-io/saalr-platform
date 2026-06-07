import type { PageContext } from 'vike/types'
import { GLOSSARY } from '../../../src/seo/content/glossary'

export function title(pageContext: PageContext): string {
  const t = GLOSSARY.find((x) => x.slug === pageContext.routeParams?.term)
  return t ? `${t.term} — SAALR options glossary` : 'SAALR'
}
