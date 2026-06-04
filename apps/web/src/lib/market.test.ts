import { describe, it, expect, vi, beforeEach } from 'vitest'
import { getIvSurface, getChain, EntitlementError } from './market'

describe('market client', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('getIvSurface GETs /v1/market/iv-surface with the ticker', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ ticker: 'SPY', spot: 1, expiries: [] }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const s = await getIvSurface('SPY')
    expect(String(fetchMock.mock.calls[0][0])).toContain('/v1/market/iv-surface?ticker=SPY')
    expect(s.ticker).toBe('SPY')
  })

  it('getChain passes the expiry param', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ ticker: 'SPY', spot: 1, contracts: [] }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await getChain('SPY', '2026-12-18')
    const url = String(fetchMock.mock.calls[0][0])
    expect(url).toContain('/v1/market/chain?ticker=SPY')
    expect(url).toContain('expiry=2026-12-18')
  })

  it('402 throws EntitlementError with the code', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ detail: { error: { code: 'ENTITLEMENT_VOL_SURFACE_REQUIRES_PRO' } } }),
        { status: 402 })))
    const err = await getIvSurface('SPY').catch((e) => e)
    expect(err).toBeInstanceOf(EntitlementError)
    expect((err as EntitlementError).code).toBe('ENTITLEMENT_VOL_SURFACE_REQUIRES_PRO')
  })
})
