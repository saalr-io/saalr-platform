import type React from 'react'
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ForecastPanel } from './ForecastPanel'
import { PriceForecastPanel } from './PriceForecastPanel'
import { MonteCarloPanel } from './MonteCarloPanel'
import { SentimentGauge } from './SentimentGauge'
import type { VolForecast, PriceForecast, MonteCarloResult, Sentiment } from '../../lib/models'

const wrap = (ui: React.ReactNode) => <MemoryRouter>{ui}</MemoryRouter>

const VOL: VolForecast = {
  horizon_days: 5, primary_model: 'garch', primary_forecast: [20, 20, 20, 20, 20], primary_ci_95: null,
  alternative_models: [], validation: { holdout_days: 40, garch_mae: 0.1, hv21_mae: 0.1, har_mae: 0.1, lift: 0 },
  model: 'garch(1,1)', iv_source: 'realized_returns', approximate: true, params: { omega: 0, alpha: 0.1, beta: 0.8 },
}
const PRICE: PriceForecast = {
  ticker: 'AAPL', market: 'US', as_of: 'x', horizon_days: 3, last_close: 100, primary_model: 'naive',
  models: [{ model: 'naive', path: [100, 100, 100], ci_95: null, expected_return_pct: 0, direction: 'flat', holdout_mae: 1, directional_accuracy: 0.5 }],
  validation: { holdout_days: 60, n_origins: 5, best_model: 'naive' }, approximate: true, disclaimer: 'x',
}
const MC = {
  pop: 0.5, ev: 1, paths: 100, histogram: { counts: [1], bin_edges: [0, 1] }, percentiles: { p5: 0, p50: 0, p95: 0 },
  max_profit_observed: 1, max_loss_observed: -1, model: 'bsm', approximate: true, seed: 0, underlying: 'AAPL',
  market: 'US', spot: 100, sigma: 0.2, sigma_source: 'garch', horizon_days: 5, rate: 0.05,
  sentiment: { applied: false },
} as MonteCarloResult
const SENT: Sentiment = {
  ticker: 'AAPL', market: 'US', score: 0.2, label: 'bullish', confident: true, n_headlines: 5, has_data: true,
  computed_at: null, as_of: null,
}

describe('ML panels carry contextual help', () => {
  it.each([
    ['vol', <ForecastPanel forecast={VOL} />],
    ['price', <PriceForecastPanel forecast={PRICE} />],
    ['mc', <MonteCarloPanel result={MC} />],
    ['sentiment', <SentimentGauge sentiment={SENT} />],
  ])('%s panel renders an info-hint', (_n, ui) => {
    render(wrap(ui))
    expect(screen.getAllByTestId('info-hint').length).toBeGreaterThan(0)
  })
})
