import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { PortfolioOverview } from './PortfolioOverview'
import type { Order } from '../../lib/oms'

const O = (over: Partial<Order> = {}): Order => ({
  order_id: 'o1', symbol: 'SPY', side: 'BUY', qty: 1, order_type: 'market', status: 'filled',
  broker_order_id: null, reject_reason_code: null, created_at: '2026-06-04T10:00:00Z', ...over,
})

describe('PortfolioOverview', () => {
  it('renders recent orders', () => {
    render(<MemoryRouter><PortfolioOverview orders={[O(), O({ order_id: 'o2', status: 'rejected' })]} /></MemoryRouter>)
    expect(screen.getByTestId('overview-order-o1')).toBeInTheDocument()
    expect(screen.getByTestId('overview-order-o2').textContent).toContain('rejected')
  })

  it('shows an empty state', () => {
    render(<MemoryRouter><PortfolioOverview orders={[]} /></MemoryRouter>)
    expect(screen.getByTestId('overview-empty')).toBeInTheDocument()
  })
})
