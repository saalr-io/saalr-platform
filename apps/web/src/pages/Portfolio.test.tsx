import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import * as oms from '../lib/oms'
import { Portfolio } from './Portfolio'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>
}

const ACC = { broker_account_id: 'a1', broker: 'paper', account_label: 'Desk', is_paper: true, status: 'active' }
const POS = { broker_account_id: 'a1', symbol: 'AAPL', option_type: null, strike: null, expiry: null, qty: 10, avg_entry_price: '150.00' }
const ORD = { order_id: 'o1', symbol: 'SPY', side: 'BUY', qty: 1, order_type: 'market', status: 'submitted', broker_order_id: null, reject_reason_code: null, created_at: '2026-06-04T10:00:00Z' }

describe('Portfolio page', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('prompts to create an account when there are none', async () => {
    vi.spyOn(oms, 'listBrokerAccounts').mockResolvedValue({ broker_accounts: [] })
    vi.spyOn(oms, 'listOrders').mockResolvedValue({ orders: [], next_cursor: null })
    render(wrap(<Portfolio />))
    await waitFor(() => expect(screen.getByTestId('no-accounts')).toBeInTheDocument())
  })

  it('closing a position places an offsetting market order', async () => {
    vi.spyOn(oms, 'listBrokerAccounts').mockResolvedValue({ broker_accounts: [ACC] as never })
    vi.spyOn(oms, 'listPositions').mockResolvedValue({ positions: [POS] as never })
    vi.spyOn(oms, 'listOrders').mockResolvedValue({ orders: [], next_cursor: null })
    const place = vi.spyOn(oms, 'placeOrder').mockResolvedValue({ order_id: 'o9', broker_order_id: null, status: 'filled', submitted_at: 'x' })
    render(wrap(<Portfolio />))
    await waitFor(() => expect(screen.getByTestId('close-btn')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('close-btn'))
    fireEvent.click(screen.getByTestId('close-yes'))
    await waitFor(() => expect(place).toHaveBeenCalled())
    const [body, key] = place.mock.calls[0]
    expect(body).toMatchObject({ broker_account_id: 'a1', symbol: 'AAPL', side: 'SELL', qty: 10, order_type: 'market' })
    expect(typeof key).toBe('string')
  })

  it('surfaces a friendly message when a cancel is not cancellable', async () => {
    vi.spyOn(oms, 'listBrokerAccounts').mockResolvedValue({ broker_accounts: [ACC] as never })
    vi.spyOn(oms, 'listPositions').mockResolvedValue({ positions: [] as never })
    vi.spyOn(oms, 'listOrders').mockResolvedValue({ orders: [ORD] as never, next_cursor: null })
    vi.spyOn(oms, 'cancelOrder').mockRejectedValue(new Error('ORDER_NOT_CANCELLABLE'))
    render(wrap(<Portfolio />))
    await waitFor(() => expect(screen.getByTestId('cancel-o1')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('cancel-o1'))
    await waitFor(() => expect(screen.getByTestId('cancel-error').textContent).toContain("can't be cancelled"))
  })
})
