import { BASE, authHeaders } from './api'
import { setToken } from './tokenStore'
import { EntitlementError, type StrategyConfig } from './strategies'

export { EntitlementError }

export interface VolForecastAlt {
  model: string
  forecast: number[]
  status: 'baseline' | 'underperforming_baseline' | 'outperforms_baseline'
  delta_mae_vs_baseline: number
}

export interface VolForecast {
  horizon_days: number
  primary_model: 'garch' | 'hv21' | 'har'
  primary_forecast: number[]
  primary_ci_95: [number, number][] | null
  alternative_models: VolForecastAlt[]
  validation: { holdout_days: number; garch_mae: number; hv21_mae: number; har_mae: number; lift: number }
  model: string
  iv_source: string
  approximate: boolean
  params: { omega: number; alpha: number; beta: number }
}

export interface Sentiment {
  ticker: string
  market: string
  score: number
  label: 'bearish' | 'neutral' | 'bullish'
  confident: boolean
  n_headlines: number
  has_data: boolean
  computed_at: string | null
  as_of: string | null
}

export interface MonteCarloRequest {
  config: StrategyConfig
  market?: string
  sigma?: number
  paths?: number
  seed?: number
  use_sentiment?: boolean
}

export interface MonteCarloResult {
  pop: number
  ev: number
  paths: number
  histogram: { counts: number[]; bin_edges: number[] }
  percentiles: { p5: number; p50: number; p95: number }
  max_profit_observed: number
  max_loss_observed: number
  model: string
  approximate: boolean
  seed: number
  underlying: string
  market: string
  spot: number
  sigma: number
  sigma_source: 'override' | 'garch'
  horizon_days: number
  rate: number
  sentiment: { applied: boolean; reason?: string; score?: number; label?: string; computed_at?: string }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(init?.headers ?? {}) },
  })
  if (res.status === 401) {
    setToken(null)
    throw new Error('unauthorized')
  }
  if (res.status === 402) {
    const body = await res.json().catch(() => ({}))
    throw new EntitlementError(body?.detail?.error?.code ?? 'ENTITLEMENT_REQUIRED')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body?.detail?.error?.code ?? `request failed: ${res.status}`)
  }
  return (await res.json()) as T
}

export function getVolForecast(ticker: string, horizon: number): Promise<VolForecast> {
  return request(`/v1/market/vol-forecast?ticker=${encodeURIComponent(ticker)}&market=US&horizon=${horizon}`)
}

export function getSentiment(ticker: string): Promise<Sentiment> {
  return request(`/v1/market/sentiment?ticker=${encodeURIComponent(ticker)}&market=US`)
}

export function runMonteCarlo(body: MonteCarloRequest): Promise<MonteCarloResult> {
  return request('/v1/strategies/montecarlo', { method: 'POST', body: JSON.stringify(body) })
}
