import { getToken, setToken } from './tokenStore'

const BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'

export interface HealthStatus {
  status: string
  db: string
}

export interface HealthResult extends HealthStatus {
  latencyMs: number
}

export interface Me {
  user: { id: string; email: string }
  tenant: { id: string; display_name: string; country_code: string }
  tier: string
  entitlements: Record<string, boolean | number>
}

function authHeaders(): Record<string, string> {
  const t = getToken()
  return t ? { Authorization: `Bearer ${t}` } : {}
}

export async function getHealth(): Promise<HealthResult> {
  const t0 = performance.now()
  const res = await fetch(`${BASE}/healthz`)
  if (!res.ok) throw new Error(`health check failed: ${res.status}`)
  const data = (await res.json()) as HealthStatus
  return { ...data, latencyMs: Math.round(performance.now() - t0) }
}

export async function getMe(): Promise<Me> {
  const res = await fetch(`${BASE}/me`, { headers: authHeaders() })
  if (res.status === 401) {
    setToken(null)
    throw new Error('unauthorized')
  }
  if (!res.ok) throw new Error(`me failed: ${res.status}`)
  return (await res.json()) as Me
}

export async function devLogin(email: string): Promise<string> {
  const res = await fetch(`${BASE}/auth/dev/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  })
  if (!res.ok) throw new Error(`login failed: ${res.status}`)
  const data = (await res.json()) as { token: string }
  return data.token
}
