import type { PageContext } from 'vike/types'
import { EXPLAINERS } from '../../../src/seo/content/strategies'

export function description(pageContext: PageContext): string {
  const slug = pageContext.routeParams?.strategy
  const content = EXPLAINERS.find((e) => e.slug === slug)
  return content?.summary ?? 'Options strategy explainers from Saalr.'
}
