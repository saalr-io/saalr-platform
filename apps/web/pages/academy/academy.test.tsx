import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import Page from './+Page'

describe('Academy index page', () => {
  it('links free lessons to /academy/<slug>', () => {
    const html = renderToStaticMarkup(<Page />)
    expect(html).toContain('href="/academy/what-is-an-option"')
    expect(html).toContain('href="/academy/implied-volatility"')
  })

  it('shows Pro module title in a locked teaser', () => {
    const html = renderToStaticMarkup(<Page />)
    expect(html).toContain('Constructing an iron condor')
  })

  it('links Pro module teaser to /app/education, not /academy/...', () => {
    const html = renderToStaticMarkup(<Page />)
    expect(html).toContain('href="/app/education"')
    expect(html).not.toContain('href="/academy/iron-condor-construction"')
  })

  it('shows Pro badge on the locked module', () => {
    const html = renderToStaticMarkup(<Page />)
    expect(html).toContain('Pro')
  })
})
