import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import * as market from '../lib/market'
import { Markets } from './Markets'

let mockMe: { entitlements: Record<string, boolean | number> } | null
vi.mock('../auth/AuthContext', () => ({ useAuth: () => ({ me: mockMe }) }))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

const SURFACE = {
  ticker: 'SPY', market: 'US', as_of: 'x', spot: 100, data_provider: 'massive', model: 'bsm',
  risk_free_source: 'fred', freshness_ms: 0,
  expiries: [{ expiry: '2026-07-17', strikes: [{ strike: 100, iv_call: 0.2, iv_put: 0.21 }] }],
}

describe('Markets page', () => {
  beforeEach(() => { vi.restoreAllMocks(); mockMe = { entitlements: { vol_surface: true } } })

  it('shows the upgrade gate for a free user and does not fetch', () => {
    mockMe = { entitlements: { vol_surface: false } }
    const spy = vi.spyOn(market, 'getIvSurface')
    render(wrap(<Markets />))
    expect(screen.getByTestId('markets-gate')).toBeInTheDocument()
    expect(spy).not.toHaveBeenCalled()
  })

  it('loads a ticker and shows the spot + tabs for an entitled user', async () => {
    vi.spyOn(market, 'getIvSurface').mockResolvedValue(SURFACE as never)
    render(wrap(<Markets />))
    fireEvent.change(screen.getByTestId('ticker-input'), { target: { value: 'SPY' } })
    fireEvent.click(screen.getByTestId('ticker-load'))
    await waitFor(() => expect(screen.getByTestId('markets-header').textContent).toMatch(/100/))
    expect(screen.getByTestId('tab-vol')).toBeInTheDocument()
    expect(screen.getByTestId('iv-smile')).toBeInTheDocument()
  })
})
