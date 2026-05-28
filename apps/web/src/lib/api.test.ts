import { describe, it, expect, vi } from 'vitest'
import { getHealth } from './api'

describe('getHealth', () => {
  it('returns parsed status with latency on 200', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ status: 'ok', db: 'ok' }), { status: 200 })),
    )
    const r = await getHealth()
    expect(r.status).toBe('ok')
    expect(r.db).toBe('ok')
    expect(typeof r.latencyMs).toBe('number')
  })

  it('throws on non-2xx', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('err', { status: 503 })),
    )
    await expect(getHealth()).rejects.toThrow()
  })
})