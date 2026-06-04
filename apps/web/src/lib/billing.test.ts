import { describe, it, expect, vi, beforeEach } from 'vitest'
import { getSubscription, startUpgrade, openPortal, EntitlementError } from './billing'

describe('billing client', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('getSubscription GETs /subscription', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({
      tier: 'free', status: 'active', current_period_end: null,
      cancel_at_period_end: false, entitlements: {}, has_customer: false,
    }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const s = await getSubscription()
    expect(String(fetchMock.mock.calls[0][0])).toContain('/subscription')
    expect(s.tier).toBe('free')
    expect(s.has_customer).toBe(false)
  })

  it('startUpgrade POSTs the tier and returns checkout_url', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ checkout_url: 'https://stripe/c/1' }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const r = await startUpgrade('pro')
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(String(url)).toContain('/subscription/upgrade')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ tier: 'pro' })
    expect(r.checkout_url).toBe('https://stripe/c/1')
  })

  it('openPortal POSTs and returns portal_url', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ portal_url: 'https://stripe/p/1' }), { status: 200 })))
    expect((await openPortal()).portal_url).toBe('https://stripe/p/1')
  })

  it('402 throws EntitlementError with the code', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ detail: { error: { code: 'FEATURE_UNAVAILABLE' } } }),
        { status: 402 })))
    const err = await startUpgrade('pro').catch((e) => e)
    expect(err).toBeInstanceOf(EntitlementError)
    expect((err as EntitlementError).code).toBe('FEATURE_UNAVAILABLE')
  })
})
