export interface HealthStatus {
  status: string
  db: string
}

export interface HealthResult extends HealthStatus {
  latencyMs: number
}

const BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'

export async function getHealth(): Promise<HealthResult> {
  const t0 = performance.now()
  const res = await fetch(`${BASE}/healthz`)
  if (!res.ok) throw new Error(`health check failed: ${res.status}`)
  const data = (await res.json()) as HealthStatus
  return { ...data, latencyMs: Math.round(performance.now() - t0) }
}