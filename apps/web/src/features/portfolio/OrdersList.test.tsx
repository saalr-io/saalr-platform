import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { OrdersList } from './OrdersList'
import type { Order } from '../../lib/oms'

const O = (over: Partial<Order> = {}): Order => ({
  order_id: 'o1', symbol: 'SPY', side: 'BUY', qty: 1, order_type: 'market', status: 'submitted',
  broker_order_id: null, reject_reason_code: null, created_at: '2026-06-04T10:00:00Z', ...over,
})

describe('OrdersList', () => {
  it('cancels a submitted order', () => {
    const onCancel = vi.fn()
    render(<OrdersList orders={[O()]} cancellingId={null} hasMore={false} onCancel={onCancel} onLoadMore={vi.fn()} />)
    fireEvent.click(screen.getByTestId('cancel-o1'))
    expect(onCancel).toHaveBeenCalledWith(expect.objectContaining({ order_id: 'o1' }))
  })

  it('shows the reject reason on a rejected order and no cancel button', () => {
    render(<OrdersList orders={[O({ order_id: 'o2', status: 'rejected', reject_reason_code: 'RISK_INSUFFICIENT_BUYING_POWER' })]}
      cancellingId={null} hasMore={false} onCancel={vi.fn()} onLoadMore={vi.fn()} />)
    expect(screen.getByTestId('order-o2').textContent).toContain('RISK_INSUFFICIENT_BUYING_POWER')
    expect(screen.queryByTestId('cancel-o2')).toBeNull()
  })

  it('empty state when no orders', () => {
    render(<OrdersList orders={[]} cancellingId={null} hasMore={false} onCancel={vi.fn()} onLoadMore={vi.fn()} />)
    expect(screen.getByTestId('orders-empty')).toBeInTheDocument()
  })
})
