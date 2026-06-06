import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import * as models from '../lib/models'
import * as strategies from '../lib/strategies'
import { Models } from './Models'

let mockMe: { entitlements: Record<string, boolean | number> } | null
vi.mock('../auth/AuthContext', () => ({ useAuth: () => ({ me: mockMe }) }))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>
}

const FORECAST: models.VolForecast = {
  horizon_days: 10, primary_model: 'garch',
  primary_forecast: Array(10).fill(20), primary_ci_95: Array(10).fill([18, 22]),
  alternative_models: [{ model: 'hv21', forecast: Array(10).fill(19), status: 'baseline', delta_mae_vs_baseline: -0.1 }],
  validation: { holdout_days: 40, garch_mae: 0.5, hv21_mae: 0.6, har_mae: 0.45, lift: 0.1 },
  model: 'garch(1,1)', iv_source: 'realized_returns', approximate: true,
  params: { omega: 0.0001, alpha: 0.08, beta: 0.9 },
}
const SENTIMENT: models.Sentiment = {
  ticker: 'AAPL', market: 'US', score: 0.3, label: 'bullish', confident: true,
  n_headlines: 8, has_data: true, computed_at: '2026-06-04T10:00:00Z', as_of: '2026-06-04T00:00:00Z',
}
const MC: models.MonteCarloResult = {
  pop: 0.6, ev: 20, paths: 10000, histogram: { counts: [1, 2], bin_edges: [-10, 0, 10] },
  percentiles: { p5: -5, p50: 1, p95: 8 }, max_profit_observed: 10, max_loss_observed: -10,
  model: 'gbm_mc', approximate: true, seed: 0, underlying: 'SPY', market: 'US', spot: 500,
  sigma: 0.2, sigma_source: 'garch', horizon_days: 14, rate: 0.04, sentiment: { applied: false, reason: 'not_requested' },
}

describe('Models page', () => {
  beforeEach(() => { vi.restoreAllMocks(); mockMe = { entitlements: { ml_forecast: true } } })

  it('gates a free user and does not fetch', () => {
    mockMe = { entitlements: { ml_forecast: false } }
    const spy = vi.spyOn(models, 'getVolForecast')
    const sentSpy = vi.spyOn(models, 'getSentiment')
    render(wrap(<Models />))
    expect(screen.getByTestId('models-gate')).toBeInTheDocument()
    expect(spy).not.toHaveBeenCalled()
    expect(sentSpy).not.toHaveBeenCalled()
  })

  it('loads a ticker and renders forecast + sentiment', async () => {
    vi.spyOn(models, 'getVolForecast').mockResolvedValue(FORECAST)
    vi.spyOn(models, 'getSentiment').mockResolvedValue(SENTIMENT)
    render(wrap(<Models />))
    fireEvent.change(screen.getByTestId('ticker-input'), { target: { value: 'AAPL' } })
    fireEvent.click(screen.getByTestId('ticker-load'))
    await waitFor(() => expect(screen.getByTestId('forecast-panel')).toBeInTheDocument())
    expect(screen.getByTestId('sentiment-label').textContent).toContain('bullish')
  })

  it('runs a Monte-Carlo simulation from a template', async () => {
    const cfg: strategies.StrategyConfig = {
      underlying: 'SPY',
      legs: [{ kind: 'option', option_type: 'CALL', side: 'BUY', strike: 500, expiry: '2026-12-18', qty: 1 }],
    }
    vi.spyOn(strategies, 'listTemplates').mockResolvedValue([{ key: 'long-call', name: 'Long Call', description: 'x', market_view: 'bullish', vol_view: 'neutral', net: 'debit', risk: 'defined', reward: 'undefined', legs: 1, complexity: 'beginner' }])
    vi.spyOn(strategies, 'buildTemplate').mockResolvedValue(cfg)
    const run = vi.spyOn(models, 'runMonteCarlo').mockResolvedValue(MC)
    render(wrap(<Models />))
    fireEvent.click(screen.getByTestId('tab-montecarlo'))
    fireEvent.change(screen.getByTestId('mc-underlying'), { target: { value: 'SPY' } })
    fireEvent.change(screen.getByTestId('mc-expiry'), { target: { value: '2026-12-18' } })
    fireEvent.change(screen.getByTestId('mc-strike'), { target: { value: '500' } })
    await waitFor(() => expect(screen.getByText('Long Call')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Long Call'))
    await waitFor(() => expect(screen.getByTestId('mc-selected')).toBeInTheDocument())
    expect(screen.getByTestId('mc-leg-0').textContent).toContain('CALL')
    fireEvent.click(screen.getByTestId('mc-run'))
    await waitFor(() => expect(run).toHaveBeenCalled())
    expect(screen.getByTestId('mc-panel')).toBeInTheDocument()
  })

  it('shows the price upsell for a Pro user (ml_forecast, no price_forecast)', async () => {
    mockMe = { entitlements: { ml_forecast: true, price_forecast: false } }
    vi.spyOn(models, 'getVolForecast').mockResolvedValue(FORECAST)
    vi.spyOn(models, 'getSentiment').mockResolvedValue(SENTIMENT)
    render(wrap(<Models />))
    fireEvent.change(screen.getByTestId('ticker-input'), { target: { value: 'AAPL' } })
    fireEvent.click(screen.getByTestId('ticker-load'))
    await waitFor(() => expect(screen.getByTestId('forecast-panel')).toBeInTheDocument())
    expect(await screen.findByTestId('price-upsell')).toBeInTheDocument()
  })

  it('does not show the upsell for a Premium user (price_forecast true)', async () => {
    mockMe = { entitlements: { ml_forecast: true, price_forecast: true } }
    vi.spyOn(models, 'getVolForecast').mockResolvedValue(FORECAST)
    vi.spyOn(models, 'getSentiment').mockResolvedValue(SENTIMENT)
    render(wrap(<Models />))
    fireEvent.change(screen.getByTestId('ticker-input'), { target: { value: 'AAPL' } })
    fireEvent.click(screen.getByTestId('ticker-load'))
    await waitFor(() => expect(screen.getByTestId('forecast-panel')).toBeInTheDocument())
    expect(screen.queryByTestId('price-upsell')).toBeNull()
  })
})
