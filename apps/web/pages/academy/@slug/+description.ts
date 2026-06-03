import type { PageContext } from 'vike/types'
import { ACADEMY_MODULES } from '../../../src/academy/modules.generated'

export function description(pageContext: PageContext): string {
  const slug = pageContext.routeParams?.slug
  const module = ACADEMY_MODULES.find((m) => m.slug === slug && m.body !== null)
  return module?.summary ?? 'Free options lessons from Saalr.'
}
