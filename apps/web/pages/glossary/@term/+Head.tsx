import { usePageContext } from 'vike-react/usePageContext'
import { GLOSSARY } from '../../../src/seo/content/glossary'
import { pageMeta } from '../../../src/seo/meta'
import { ORIGIN } from './origin'

export default function Head() {
  const pageContext = usePageContext()
  const t = GLOSSARY.find((x) => x.slug === pageContext.routeParams?.term)
  if (!t) return null
  const meta = pageMeta({
    title: `${t.term} — SAALR options glossary`,
    description: t.short,
    canonical: `${ORIGIN}/glossary/${t.slug}`,
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
