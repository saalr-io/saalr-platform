import { pageMeta } from '../../src/seo/meta'
import { ORIGIN } from '../../src/seo/origin'

const TITLE = 'OptionsAcademy — Saalr'
const DESC = 'Free, plain-English lessons on options — from what an option is to how volatility is priced in.'

export default function Head() {
  const meta = pageMeta({ title: TITLE, description: DESC, canonical: `${ORIGIN}/academy`, type: 'website' })
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
