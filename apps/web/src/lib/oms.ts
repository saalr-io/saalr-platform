import { BASE, authHeaders } from './api'
import { setToken } from './tokenStore'
import { EntitlementError } from './strategies'

export { EntitlementError }

export interface BrokerAccount {
  broker_account_id: string
  broker: string
  account_label: string
  is_paper: boolean
  status: string
}

export interface Position {
  broker_account_id: string
  symbol: string
  option_type: 'CALL' | 'PUT' | null
  strike: string | null
  expiry: string | null
  qty: number
  avg_entry_price: string
}

export interface Order {
  order_id: string
  symbol: string
  side: string
  qty: number
  order_type: string
  status: string
  broker_order_id: string | null
  reject_reason_code: string | null
  created_at: string
}

export interface OrderResult {
  order_id: string
  broker_order_id: string | null
  status: string
  submitted_at: string
}

export interface OrderCreate {
  broker_account_id: string
  symbol: string
  side: 'BUY' | 'SELL'
  qty: number
  order_type: 'market' | 'limit'
  option_type?: 'CALL' | 'PUT'
  strike?: number
  expiry?: string
  limit_price?: number
  time_in_force?: 'day'
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

export function listBrokerAccounts(): Promise<{ broker_accounts: BrokerAccount[] }> {
  return request('/v1/broker-accounts')
}

export function createBrokerAccount(label: string): Promise<BrokerAccount> {
  return request('/v1/broker-accounts', {
    method: 'POST',
    body: JSON.stringify({ broker: 'paper', account_label: label, is_paper: true }),
  })
}

export function listPositions(brokerAccountId: string): Promise<{ positions: Position[] }> {
  return request(`/v1/positions?broker_account_id=${encodeURIComponent(brokerAccountId)}`)
}

export function listOrders(cursor?: string): Promise<{ orders: Order[]; next_cursor: string | null }> {
  return request(`/v1/orders?limit=20${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`)
}

export function placeOrder(body: OrderCreate, idempotencyKey: string): Promise<OrderResult> {
  return request('/v1/orders', {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify(body),
  })
}

export function cancelOrder(orderId: string): Promise<OrderResult> {
  return request(`/v1/orders/${encodeURIComponent(orderId)}/cancel`, { method: 'POST' })
}
