import { describe, it, expect, vi, beforeEach } from 'vitest'
import { listBrokerAccounts, createBrokerAccount, listPositions, listOrders, placeOrder, cancelOrder } from './oms'

describe('oms client', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('listBrokerAccounts GETs /v1/broker-accounts', async () => {
    const f = vi.fn(async () => new Response(JSON.stringify({ broker_accounts: [] }), { status: 200 }))
    vi.stubGlobal('fetch', f)
    await listBrokerAccounts()
    expect(String((f.mock.calls as unknown as [string, RequestInit?][])[0][0])).toContain('/v1/broker-accounts')
  })

  it('createBrokerAccount POSTs a paper account', async () => {
    const f = vi.fn(async () => new Response(JSON.stringify({ broker_account_id: 'a1' }), { status: 200 }))
    vi.stubGlobal('fetch', f)
    await createBrokerAccount('My desk')
    const init = (f.mock.calls as unknown as [string, RequestInit?][])[0][1] as RequestInit
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ broker: 'paper', account_label: 'My desk', is_paper: true })
  })

  it('listPositions passes the account id', async () => {
    const f = vi.fn(async () => new Response(JSON.stringify({ positions: [] }), { status: 200 }))
    vi.stubGlobal('fetch', f)
    await listPositions('a1')
    expect(String((f.mock.calls as unknown as [string, RequestInit?][])[0][0])).toContain('/v1/positions?broker_account_id=a1')
  })

  it('listOrders adds a cursor when given', async () => {
    const f = vi.fn(async () => new Response(JSON.stringify({ orders: [], next_cursor: null }), { status: 200 }))
    vi.stubGlobal('fetch', f)
    await listOrders('CUR')
    expect(String((f.mock.calls as unknown as [string, RequestInit?][])[0][0])).toContain('cursor=CUR')
  })

  it('placeOrder POSTs with the Idempotency-Key header and body', async () => {
    const f = vi.fn(async () => new Response(JSON.stringify({ order_id: 'o1', status: 'submitted' }), { status: 200 }))
    vi.stubGlobal('fetch', f)
    await placeOrder({ broker_account_id: 'a1', symbol: 'SPY', side: 'BUY', qty: 1, order_type: 'market' }, 'KEY-1')
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit]
    expect(String(url)).toContain('/v1/orders')
    expect((init.headers as Record<string, string>)['Idempotency-Key']).toBe('KEY-1')
    expect(JSON.parse(init.body as string).symbol).toBe('SPY')
  })

  it('cancelOrder POSTs to the cancel path', async () => {
    const f = vi.fn(async () => new Response(JSON.stringify({ order_id: 'o1', status: 'cancelled' }), { status: 200 }))
    vi.stubGlobal('fetch', f)
    await cancelOrder('o1')
    expect(String((f.mock.calls as unknown as [string, RequestInit?][])[0][0])).toContain('/v1/orders/o1/cancel')
  })

  it('a 422 throws Error with the RISK code', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ detail: { error: { code: 'RISK_INSUFFICIENT_BUYING_POWER' } } }), { status: 422 })))
    await expect(placeOrder({ broker_account_id: 'a1', symbol: 'SPY', side: 'BUY', qty: 1, order_type: 'market' }, 'K'))
      .rejects.toThrow('RISK_INSUFFICIENT_BUYING_POWER')
  })
})
