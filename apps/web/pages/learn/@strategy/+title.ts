import type { PageContext } from 'vike/types'
import { EXPLAINERS } from '../../../src/seo/content/strategies'

export function title(pageContext: PageContext): string {
  const slug = pageContext.routeParams?.strategy
  const content = EXPLAINERS.find((e) => e.slug === slug)
  return content ? `${content.title} — Saalr` : 'Saalr'
}
