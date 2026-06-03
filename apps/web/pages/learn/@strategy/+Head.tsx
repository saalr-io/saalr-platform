import { usePageContext } from 'vike-react/usePageContext'
import { EXPLAINERS } from '../../../src/seo/content/strategies'
import { pageMeta } from '../../../src/seo/meta'
import { ORIGIN } from './origin'

export default function Head() {
  const pageContext = usePageContext()
  const slug = pageContext.routeParams?.strategy
  const content = EXPLAINERS.find((e) => e.slug === slug)
  if (!content) return null
  const meta = pageMeta({
    title: `${content.title} — SAALR`,
    description: content.summary,
    canonical: `${ORIGIN}/learn/${content.slug}`,
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
