import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PayoffChart } from './PayoffChart'

const expiration = [
  { spot: 80, pnl: -400 }, { spot: 100, pnl: -400 },
  { spot: 110, pnl: 600 }, { spot: 130, pnl: 600 },
]

describe('PayoffChart', () => {
  it('renders the expiration polyline', () => {
    render(<PayoffChart expirationCurve={expiration} breakevens={[104]} />)
    expect(screen.getByTestId('payoff-expiry')).toBeInTheDocument()
  })

  it('renders the target-date path only when provided', () => {
    const { rerender } = render(<PayoffChart expirationCurve={expiration} breakevens={[]} />)
    expect(screen.queryByTestId('payoff-target')).not.toBeInTheDocument()
    rerender(<PayoffChart expirationCurve={expiration} targetDateCurve={expiration} breakevens={[]} />)
    expect(screen.getByTestId('payoff-target')).toBeInTheDocument()
  })

  it('renders a breakeven marker per breakeven', () => {
    render(<PayoffChart expirationCurve={expiration} breakevens={[104, 116]} />)
    expect(screen.getAllByTestId('payoff-be')).toHaveLength(2)
  })

  it('renders the spot marker when spot given', () => {
    render(<PayoffChart expirationCurve={expiration} breakevens={[]} spot={100} />)
    expect(screen.getByTestId('payoff-spot')).toBeInTheDocument()
  })
})
