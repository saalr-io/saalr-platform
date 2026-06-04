import type { PageContext } from 'vike/types'
import { GLOSSARY } from '../../../src/seo/content/glossary'

export function description(pageContext: PageContext): string {
  const t = GLOSSARY.find((x) => x.slug === pageContext.routeParams?.term)
  return t?.short ?? 'Options glossary term.'
}
