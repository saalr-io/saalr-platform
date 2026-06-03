import { usePageContext } from 'vike-react/usePageContext'
import { ACADEMY_MODULES } from '../../../src/academy/modules.generated'
import { pageMeta } from '../../../src/seo/meta'
import { ORIGIN } from './origin'

export default function Head() {
  const pageContext = usePageContext()
  const slug = pageContext.routeParams?.slug
  const module = ACADEMY_MODULES.find((m) => m.slug === slug && m.body !== null)
  if (!module) return null
  const meta = pageMeta({
    title: `${module.title} — SAALR`,
    description: module.summary,
    canonical: `${ORIGIN}/academy/${module.slug}`,
  })
  return (
    <>
      <link rel="canonical" href={meta.canonical} />
      {Object.entries(meta.og).map(([k, v]) => (
        <meta key={k} property={k} content={v} />
      ))}
      {Object.entries(meta.twitter).map(([k, v]) => (
        <meta key={k} name={k} content={v} />
      ))}
    </>
  )
}
