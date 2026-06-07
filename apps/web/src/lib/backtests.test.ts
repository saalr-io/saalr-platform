import { describe, it, expect, vi, afterEach } from 'vitest'
import { createBacktest, getBacktest } from './backtests'

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({ ok: status >= 200 && status < 300, status, json: async () => body })
}
afterEach(() => vi.unstubAllGlobals())

describe('backtests client', () => {
  it('createBacktest POSTs with an Idempotency-Key and returns 202 shape', async () => {
    const f = mockFetch(202, { backtest_id: 'b1', status: 'queued', estimated_duration_seconds: 12, poll_url: '/v1/backtests/b1' })
    vi.stubGlobal('fetch', f)
    const r = await createBacktest('s1', { start_date: '2023-01-01', end_date: '2025-01-01', initial_capital: 100000, include_costs: true }, 'idem-1')
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toContain('/v1/strategies/s1/backtest')
    expect(init.method).toBe('POST')
    expect((init.headers as Record<string, string>)['Idempotency-Key']).toBe('idem-1')
    expect(r.backtest_id).toBe('b1')
  })

  it('getBacktest returns the succeeded payload with metrics + equity_series', async () => {
    const f = mockFetch(200, { backtest_id: 'b1', status: 'succeeded', metrics: { sharpe: 0.6 }, equity_series: [{ date: '2023-01-03', equity: 100000 }] })
    vi.stubGlobal('fetch', f)
    const r = await getBacktest('b1')
    expect(r.status).toBe('succeeded')
    expect(r.equity_series?.[0].equity).toBe(100000)
  })

  it('throws Error(code) on a non-ok status', async () => {
    vi.stubGlobal('fetch', mockFetch(404, { detail: { error: { code: 'RESOURCE_NOT_FOUND' } } }))
    await expect(getBacktest('nope')).rejects.toThrow('RESOURCE_NOT_FOUND')
  })
})
