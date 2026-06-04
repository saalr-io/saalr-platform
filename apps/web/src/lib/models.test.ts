import { describe, it, expect, vi, afterEach } from 'vitest'
import { getVolForecast, getSentiment, runMonteCarlo, EntitlementError } from './models'

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({ ok: status >= 200 && status < 300, status, json: async () => body })
}

afterEach(() => vi.unstubAllGlobals())

describe('models client', () => {
  it('getVolForecast hits the vol-forecast endpoint with horizon', async () => {
    const f = mockFetch(200, { primary_model: 'garch' })
    vi.stubGlobal('fetch', f)
    await getVolForecast('SPY', 20)
    expect(f.mock.calls[0][0] as string).toContain('/v1/market/vol-forecast?ticker=SPY&market=US&horizon=20')
  })

  it('getSentiment hits the sentiment endpoint', async () => {
    const f = mockFetch(200, { has_data: false })
    vi.stubGlobal('fetch', f)
    await getSentiment('AAPL')
    expect(f.mock.calls[0][0] as string).toContain('/v1/market/sentiment?ticker=AAPL&market=US')
  })

  it('runMonteCarlo POSTs the body', async () => {
    const f = mockFetch(200, { pop: 0.5 })
    vi.stubGlobal('fetch', f)
    await runMonteCarlo({ config: { underlying: 'SPY', legs: [] }, paths: 5000, use_sentiment: true })
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toContain('/v1/strategies/montecarlo')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toMatchObject({ paths: 5000, use_sentiment: true })
  })

  it('throws EntitlementError on 402', async () => {
    vi.stubGlobal('fetch', mockFetch(402, { detail: { error: { code: 'ENTITLEMENT_REQUIRED' } } }))
    await expect(getVolForecast('SPY', 10)).rejects.toBeInstanceOf(EntitlementError)
  })

  it('throws Error(code) on 422', async () => {
    vi.stubGlobal('fetch', mockFetch(422, { detail: { error: { code: 'INSUFFICIENT_HISTORY' } } }))
    await expect(getVolForecast('SPY', 10)).rejects.toThrow('INSUFFICIENT_HISTORY')
  })
})
