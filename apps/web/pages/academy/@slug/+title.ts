import type { PageContext } from 'vike/types'
import { ACADEMY_MODULES } from '../../../src/academy/modules.generated'

export function title(pageContext: PageContext): string {
  const slug = pageContext.routeParams?.slug
  const module = ACADEMY_MODULES.find((m) => m.slug === slug && m.body !== null)
  return module ? `${module.title} — Saalr` : 'Saalr'
}
