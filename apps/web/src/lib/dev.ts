import { BASE, authHeaders } from './api'

export interface SeedBarsResult {
  symbol: string
  rows_upserted: number
  first: string
  last: string
}

export interface SeedChainResult {
  ticker: string
  as_of: string
  contracts: number
  total_snapshots: number
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data?.detail?.error?.message ?? data?.detail?.error?.code ?? `request failed: ${res.status}`)
  }
  return (await res.json()) as T
}

export function seedBars(ticker: string, days: number): Promise<SeedBarsResult> {
  return post('/v1/dev/seed/bars', { ticker, days })
}

export function seedChain(ticker: string): Promise<SeedChainResult> {
  return post('/v1/dev/seed/chain', { ticker })
}
