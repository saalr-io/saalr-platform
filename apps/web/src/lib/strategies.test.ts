import { describe, it, expect, vi, beforeEach } from 'vitest'
import { analyzeStrategy, listTemplates, EntitlementError } from './strategies'

const cfg = { underlying: 'AAPL', legs: [
  { kind: 'option' as const, option_type: 'CALL' as const, side: 'BUY' as const,
    strike: 100, expiry: '2026-12-18', qty: 1, entry_price: 6 },
] }

describe('strategies client', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('analyze returns parsed result on 200', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(
      JSON.stringify({ expiration_curve: [{ spot: 100, pnl: -400 }], breakevens: [104],
        max_profit: 600, max_loss: -400, unbounded_profit: false, unbounded_loss: false,
        net_premium: 400, risk_reward: 1.5 }), { status: 200 })))
    const r = await analyzeStrategy(cfg, { live: false })
    expect(r.breakevens).toEqual([104])
    expect(r.max_profit).toBe(600)
  })

  it('throws EntitlementError on 402', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(
      JSON.stringify({ detail: { error: { code: 'ENTITLEMENT_VOL_SURFACE_REQUIRES_PRO' } } }),
      { status: 402 })))
    await expect(analyzeStrategy(cfg, { live: true })).rejects.toBeInstanceOf(EntitlementError)
  })

  it('listTemplates returns the array', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(
      JSON.stringify({ templates: [{ key: 'iron_condor', name: 'Iron Condor',
        category: 'neutral', description: '...' }] }), { status: 200 })))
    const t = await listTemplates()
    expect(t[0].key).toBe('iron_condor')
  })
})
