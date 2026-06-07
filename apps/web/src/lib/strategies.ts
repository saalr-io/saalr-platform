import { BASE, authHeaders } from './api'
import { setToken } from './tokenStore'

export type OptionType = 'CALL' | 'PUT'
export type Side = 'BUY' | 'SELL'

export interface OptionLeg {
  kind: 'option'; option_type: OptionType; side: Side
  strike: number; expiry: string; qty: number; entry_price?: number | null
}
export interface EquityLeg { kind: 'equity'; side: Side; qty: number; entry_price?: number | null }
export interface CashLeg { kind: 'cash'; amount: number }
export type Leg = OptionLeg | EquityLeg | CashLeg

export interface StrategyConfig { underlying: string; legs: Leg[] }

export interface Strategy {
  strategy_id: string; name: string; description: string | null
  state: string; market: string; config: StrategyConfig
  created_at: string; updated_at: string
}

export interface TemplateDescriptor {
  key: string
  name: string
  description: string
  market_view: 'bullish' | 'bearish' | 'neutral' | 'volatile'
  vol_view: 'long_vol' | 'short_vol' | 'neutral'
  net: 'debit' | 'credit' | 'mixed'
  risk: 'defined' | 'undefined'
  reward: 'defined' | 'undefined'
  legs: number
  complexity: 'beginner' | 'intermediate' | 'advanced'
}

export interface CurvePoint { spot: number; pnl: number }

export interface AnalyzeResult {
  expiration_curve: CurvePoint[]
  breakevens: number[]
  max_profit: number | null
  max_loss: number | null
  unbounded_profit: boolean
  unbounded_loss: boolean
  net_premium: number
  risk_reward: number | null
  net_greeks?: { delta: number; gamma: number; theta: number; vega: number; rho: number }
  probability_of_profit?: { pop: number | null; method: string; approximate: boolean }
  target_date_curve?: CurvePoint[]
  spot?: number
  data_provider?: string
  risk_free_source?: string
}

export class EntitlementError extends Error {
  code: string
  constructor(code: string) {
    super('entitlement required')
    this.name = 'EntitlementError'
    this.code = code
  }
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

export function listStrategies(cursor?: string): Promise<{ strategies: Strategy[]; next_cursor: string | null }> {
  return request(`/v1/strategies${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''}`)
}
export function getStrategy(id: string): Promise<Strategy> {
  return request(`/v1/strategies/${id}`)
}
export function createStrategy(body: { name: string; description?: string; market?: string; config: StrategyConfig }): Promise<Strategy> {
  return request('/v1/strategies', { method: 'POST', body: JSON.stringify(body) })
}
export function transitionStrategy(id: string, target_state: string): Promise<Strategy> {
  return request(`/v1/strategies/${id}/transition`, { method: 'POST', body: JSON.stringify({ target_state }) })
}
export function archiveStrategy(id: string): Promise<Strategy> {
  return request(`/v1/strategies/${id}`, { method: 'DELETE' })
}
export async function listTemplates(): Promise<TemplateDescriptor[]> {
  const r = await request<{ templates: TemplateDescriptor[] }>('/v1/strategies/templates')
  return r.templates
}
export async function buildTemplate(
  key: string, params: { underlying: string; expiry: string; atm_strike: number; width?: number },
): Promise<StrategyConfig> {
  const r = await request<{ underlying: string; legs: Leg[] }>(
    `/v1/strategies/templates/${key}/build`, { method: 'POST', body: JSON.stringify(params) })
  return { underlying: r.underlying, legs: r.legs }
}
export function analyzeStrategy(
  config: StrategyConfig, opts: { target_date?: string; live?: boolean },
): Promise<AnalyzeResult> {
  return request('/v1/strategies/analyze', {
    method: 'POST',
    body: JSON.stringify({ config, target_date: opts.target_date, live: opts.live ?? false }),
  })
}
