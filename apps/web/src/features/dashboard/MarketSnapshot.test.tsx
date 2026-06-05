import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { MarketSnapshot } from './MarketSnapshot'
import type { IvSurface } from '../../lib/market'

const SURFACE: IvSurface = {
  ticker: 'SPY', market: 'US', as_of: 'x', spot: 100, data_provider: 'massive', model: 'bsm',
  risk_free_source: 'fred', freshness_ms: 0,
  expiries: [{ expiry: '2026-07-17', strikes: [
    { strike: 95, iv_call: 0.22, iv_put: 0.24 },
    { strike: 100, iv_call: 0.20, iv_put: 0.21 }] }],
}

describe('MarketSnapshot', () => {
  it('shows spot and ATM IV from the surface', () => {
    render(<MarketSnapshot symbol="SPY" surface={SURFACE} entitled={true} loading={false} />)
    expect(screen.getByTestId('snapshot').textContent).toContain('100.00')
    expect(screen.getByTestId('snapshot-iv').textContent).toContain('20.5%')
  })

  it('shows an upgrade hint when not entitled', () => {
    render(<MemoryRouter><MarketSnapshot symbol="SPY" surface={null} entitled={false} loading={false} /></MemoryRouter>)
    expect(screen.getByTestId('upgrade-hint')).toBeInTheDocument()
  })

  it('prompts when there is no symbol', () => {
    render(<MarketSnapshot symbol="" surface={null} entitled={true} loading={false} />)
    expect(screen.getByTestId('snapshot-empty')).toBeInTheDocument()
  })
})
