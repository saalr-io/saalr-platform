import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import * as oms from '../lib/oms'
import * as models from '../lib/models'
import * as market from '../lib/market'
import { Dashboard } from './Dashboard'

let mockMe: { user: { email: string }; tier: string; entitlements: Record<string, boolean | number> } | null
vi.mock('../auth/AuthContext', () => ({ useAuth: () => ({ me: mockMe }) }))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>
}

const ACC = { broker_account_id: 'a1', broker: 'paper', account_label: 'Desk', is_paper: true, status: 'active' }
const POS = { broker_account_id: 'a1', symbol: 'AAPL', option_type: null, strike: null, expiry: null, qty: 10, avg_entry_price: '150.00' }
const ORD = { order_id: 'o1', symbol: 'AAPL', side: 'BUY', qty: 10, order_type: 'market', status: 'filled', broker_order_id: null, reject_reason_code: null, created_at: '2026-06-04T10:00:00Z' }

describe('Dashboard', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    mockMe = { user: { email: 'a@b.com' }, tier: 'pro', entitlements: { ml_forecast: true, vol_surface: true } }
    vi.spyOn(oms, 'listBrokerAccounts').mockResolvedValue({ broker_accounts: [ACC] as never })
    vi.spyOn(oms, 'listPositions').mockResolvedValue({ positions: [POS] as never })
    vi.spyOn(oms, 'listOrders').mockResolvedValue({ orders: [ORD] as never, next_cursor: null })
  })

  it('gates the watchlist and snapshot for a free user without fetching gated data', async () => {
    mockMe = { user: { email: 'free@b.com' }, tier: 'free', entitlements: { ml_forecast: false, vol_surface: false } }
    const fc = vi.spyOn(models, 'getVolForecast')
    const iv = vi.spyOn(market, 'getIvSurface')
    render(wrap(<Dashboard />))
    // Wait for both gated cards' nudges — this only happens after OMS settles and `symbols`
    // is populated, so the no-fetch assertions below prove the guard held with a live symbol.
    await waitFor(() => expect(screen.getAllByTestId('upgrade-hint').length).toBeGreaterThanOrEqual(2))
    expect(screen.getByTestId('portfolio-overview')).toBeInTheDocument()
    expect(fc).not.toHaveBeenCalled()
    expect(iv).not.toHaveBeenCalled()
  })

  it('shows a watchlist row with forecast + sentiment for an entitled user', async () => {
    vi.spyOn(models, 'getVolForecast').mockResolvedValue({
      horizon_days: 10, primary_model: 'garch', primary_forecast: [20, 22], primary_ci_95: null,
      alternative_models: [], validation: { holdout_days: 40, garch_mae: 0.5, hv21_mae: 0.6, har_mae: 0.45, lift: 0.1 },
      model: 'garch(1,1)', iv_source: 'realized_returns', approximate: true, params: { omega: 0.0001, alpha: 0.08, beta: 0.9 },
    })
    vi.spyOn(models, 'getSentiment').mockResolvedValue({
      ticker: 'AAPL', market: 'US', score: 0.4, label: 'bullish', confident: true, n_headlines: 5,
      has_data: true, computed_at: '2026-06-04T10:00:00Z', as_of: '2026-06-04T00:00:00Z',
    })
    vi.spyOn(market, 'getIvSurface').mockResolvedValue({
      ticker: 'AAPL', market: 'US', as_of: 'x', spot: 150, data_provider: 'massive', model: 'bsm',
      risk_free_source: 'fred', freshness_ms: 0,
      expiries: [{ expiry: '2026-07-17', strikes: [{ strike: 150,
        calls: { price: 1, delta: 0.5, gamma: 0.01, theta: -0.02, vega: 0.1, rho: 0.05, iv: 0.2 },
        puts: { price: 1, delta: -0.5, gamma: 0.01, theta: -0.02, vega: 0.1, rho: -0.05, iv: 0.22 } }] }],
    } as never)
    render(wrap(<Dashboard />))
    await waitFor(() => expect(screen.getByTestId('watch-AAPL')).toBeInTheDocument())
    expect(screen.getByTestId('watch-AAPL').textContent).toContain('21.0%')
    expect(screen.getByTestId('watch-AAPL').textContent).toContain('bullish')
  })
})
