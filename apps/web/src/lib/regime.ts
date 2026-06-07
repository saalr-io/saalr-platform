import { BASE, authHeaders } from './api'
import { setToken } from './tokenStore'

export type Direction = 'strong_bullish' | 'bullish' | 'neutral' | 'bearish' | 'strong_bearish'
export type VolLevel = 'low' | 'normal' | 'high'
export type Momentum = 'trending' | 'range_bound'

export interface Signal { label: string; detail: string }
export interface PremiumSignal { label: string; available: boolean; detail: string; score?: number; n_headlines?: number }
export interface PremiumSignals { vol_trend: PremiumSignal; sentiment: PremiumSignal }

export interface Regime {
  direction: Signal & { score: number }
  volatility: Signal & { percentile: number; realized_vol: number }
  momentum: Signal & { efficiency_ratio: number }
  headline: string
  last_close: number
  n_closes: number
  premium_available: boolean
  premium: PremiumSignals | null
}

export interface Recommendation {
  template_key: string
  name: string
  score: number
  market_view: string
  vol_view: string
  net: string
  risk: string
  complexity: string
  rationale: string
}

export interface RegimeResponse {
  ticker: string
  market: string
  as_of: string
  approximate: boolean
  regime: Regime
  recommendations: Recommendation[]
}

async function request<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { headers: { ...authHeaders() } })
  if (res.status === 401) {
    setToken(null)
    throw new Error('unauthorized')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body?.detail?.error?.code ?? `request failed: ${res.status}`)
  }
  return (await res.json()) as T
}

export function getRegime(ticker: string, market = 'US'): Promise<RegimeResponse> {
  return request(`/v1/market/regime?ticker=${encodeURIComponent(ticker)}&market=${market}`)
}
