import { describe, it, expect } from 'vitest'
import { breadcrumbFor } from './nav'

describe('breadcrumbFor', () => {
  it('returns no crumbs on the dashboard root', () => {
    expect(breadcrumbFor('/')).toEqual([])
  })

  it('builds Home > Section > Page for a top-level page', () => {
    expect(breadcrumbFor('/strategies')).toEqual([
      { label: 'Home', to: '/' },
      { label: 'Trade' },
      { label: 'Strategies' },
    ])
  })

  it('uses the canonical sidebar label for the current page', () => {
    expect(breadcrumbFor('/markets')).toEqual([
      { label: 'Home', to: '/' },
      { label: 'Trade' },
      { label: 'Markets & Vol' },
    ])
  })

  it('links ancestors and leaves the current page as plain text for a sub-route', () => {
    expect(breadcrumbFor('/billing/success')).toEqual([
      { label: 'Home', to: '/' },
      { label: 'System' },
      { label: 'Billing', to: '/billing' },
      { label: 'Success' },
    ])
  })

  it('omits the section crumb for a route that is not in the sidebar', () => {
    expect(breadcrumbFor('/start')).toEqual([
      { label: 'Home', to: '/' },
      { label: 'Get Started' },
    ])
  })

  it('ignores a trailing slash', () => {
    expect(breadcrumbFor('/strategies/')).toEqual([
      { label: 'Home', to: '/' },
      { label: 'Trade' },
      { label: 'Strategies' },
    ])
  })
})
