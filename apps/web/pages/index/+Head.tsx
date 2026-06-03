import { pageMeta } from '../../src/seo/meta'
import { ORIGIN } from '../../src/seo/origin'

export default function Head() {
  const meta = pageMeta({
    title: 'SAALR — Research-grade options analytics',
    description:
      'Build and price multi-leg options strategies, study volatility, run backtests, and read multi-agent research notes — from one fast terminal.',
    canonical: `${ORIGIN}/`,
    type: 'website',
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
