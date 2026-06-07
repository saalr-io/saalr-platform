import { pageMeta } from '../../src/seo/meta'
import { ORIGIN } from './origin'

export default function Head() {
  const meta = pageMeta({
    title: 'Options glossary — SAALR',
    description: 'Plain-English definitions of options terms, each with examples and authoritative sources.',
    canonical: `${ORIGIN}/glossary`,
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
