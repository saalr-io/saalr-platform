import { describe, it, expect } from 'vitest'
import { buildLlmsFullTxt, explainerToText, glossaryTermToText } from './llms'
import { EXPLAINERS } from '../seo/content/strategies'
import { GLOSSARY } from '../seo/content/glossary'

const SITE = 'https://saalr.com'

describe('llms-full', () => {
  it('explainerToText includes the summary and FAQ answers', () => {
    const e = EXPLAINERS[0]
    const txt = explainerToText(e)
    expect(txt).toContain(e.summary)
    expect(txt).toContain(e.faq[0].a)
  })

  it('glossaryTermToText includes the definition, FAQ, and a source URL', () => {
    const t = GLOSSARY.find((x) => x.slug === 'theta')!
    const txt = glossaryTermToText(t)
    expect(txt).toContain(t.short)
    expect(txt).toContain(t.faq[0].a)
    expect(txt).toContain(t.sources[0].url)
  })

  it('buildLlmsFullTxt concatenates sections and headings', () => {
    const out = buildLlmsFullTxt(SITE, 'Saalr', 'tagline', [
      { heading: 'Glossary', entries: [{ title: 'Theta', url: '/glossary/theta', body: 'BODY-THETA' }] },
    ])
    expect(out).toContain('# Saalr')
    expect(out).toContain('## Glossary')
    expect(out).toContain('### Theta')
    expect(out).toContain(`${SITE}/glossary/theta`)
    expect(out).toContain('BODY-THETA')
  })

  it('omits a Pro academy body when the caller filters it out (leak guard)', () => {
    const out = buildLlmsFullTxt(SITE, 'Saalr', 'tagline', [
      { heading: 'OptionsAcademy', entries: [{ title: 'Free lesson', url: '/academy/x', body: 'FREE-BODY' }] },
    ])
    expect(out).toContain('FREE-BODY')
    expect(out).not.toContain('PRO-ONLY-BODY')
  })
})
