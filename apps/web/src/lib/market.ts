import { BASE, authHeaders } from './api'
import { setToken } from './tokenStore'
import { EntitlementError } from './strategies'

export { EntitlementError }

export interface Greeks {
  price: number
  delta: number
  gamma: number
  theta: number
  vega: number
  rho: number
  iv: number
}

// The iv-surface endpoint returns per-strike call/put IV directly (decimals, nullable when
// the BSM IV solve fails for a deep ITM/OTM contract) — NOT full Greeks objects.
export interface IvStrike { strike: number; iv_call: number | null; iv_put: number | null }
export interface IvExpiry { expiry: string; strikes: IvStrike[] }

export interface IvSurface {
  ticker: string
  market: string
  as_of: string
  spot: number
  expiries: IvExpiry[]
  data_provider: string
  model: string
  risk_free_source: string
  freshness_ms: number
}

export type OiWindow = 'day' | '1h' | '3h' | '4h'

export interface OiBaseline {
  ts: string
  elapsed_label: string
}

export interface Contract {
  expiry: string
  strike: number
  type: 'CALL' | 'PUT'
  bid: number
  ask: number
  last: number
  volume: number
  open_interest: number
  oi_change?: Record<OiWindow, number | null>
  ours: Greeks
  vendor: { iv: number; delta: number; gamma: number; theta: number; vega: number }
}

export interface Chain {
  ticker: string
  market: string
  as_of: string
  spot: number
  model: string
  risk_free_source: string
  contracts: Contract[]
  oi_baselines?: Record<OiWindow, OiBaseline | null>
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { headers: { ...authHeaders() } })
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

export function getIvSurface(ticker: string): Promise<IvSurface> {
  return get(`/v1/market/iv-surface?ticker=${encodeURIComponent(ticker)}`)
}

export function getChain(ticker: string, expiry: string): Promise<Chain> {
  return get(`/v1/market/chain?ticker=${encodeURIComponent(ticker)}&expiry=${encodeURIComponent(expiry)}`)
}
