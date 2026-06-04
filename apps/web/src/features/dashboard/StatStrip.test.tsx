import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatStrip } from './StatStrip'

describe('StatStrip', () => {
  it('shows the email and the three counts', () => {
    render(<StatStrip email="a@b.com" tier="pro" accounts={2} positions={5} workingOrders={1} />)
    expect(screen.getByText(/a@b\.com/)).toBeInTheDocument()
    expect(screen.getByTestId('stat-accounts').textContent).toBe('2')
    expect(screen.getByTestId('stat-positions').textContent).toBe('5')
    expect(screen.getByTestId('stat-orders').textContent).toBe('1')
  })
})
