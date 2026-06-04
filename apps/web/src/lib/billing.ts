import { BASE, authHeaders } from './api'
import { setToken } from './tokenStore'
import { EntitlementError } from './strategies'
import type { TierName } from './tiers'

export { EntitlementError }

export interface Subscription {
  tier: TierName
  status: string
  current_period_end: string | null
  cancel_at_period_end: boolean
  entitlements: Record<string, boolean | number>
  has_customer: boolean
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

export function getSubscription(): Promise<Subscription> {
  return request('/subscription')
}

export function startUpgrade(tier: 'pro' | 'premium'): Promise<{ checkout_url: string }> {
  return request('/subscription/upgrade', { method: 'POST', body: JSON.stringify({ tier }) })
}

export function openPortal(): Promise<{ portal_url: string }> {
  return request('/subscription/portal', { method: 'POST' })
}

// Full-page navigation to Stripe — isolated so tests can spy on it without navigating.
export function redirectTo(url: string): void {
  window.location.assign(url)
}
