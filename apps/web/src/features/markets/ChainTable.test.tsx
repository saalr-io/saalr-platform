import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ChainTable } from './ChainTable'
import type { Contract, Greeks } from '../../lib/market'

const G = (iv: number): Greeks => ({ price: 1, delta: 0.5, gamma: 0.01, theta: -0.02, vega: 0.1, rho: 0.05, iv })
const C = (strike: number, type: 'CALL' | 'PUT', iv: number): Contract => ({
  expiry: '2026-12-18', strike, type, bid: 1, ask: 1.2, last: 1.1, volume: 10, open_interest: 99,
  ours: G(iv), vendor: { iv: iv - 0.001, delta: 0.5, gamma: 0.01, theta: -0.02, vega: 0.1 },
})

describe('ChainTable', () => {
  it('pivots a call and a put at the same strike onto one row', () => {
    render(<ChainTable contracts={[C(100, 'CALL', 0.2), C(100, 'PUT', 0.25)]} spot={101} />)
    const row = screen.getByTestId('chain-row-100')
    expect(row.textContent).toContain('20.0%')
    expect(row.textContent).toContain('25.0%')
  })

  it('highlights the ATM strike (nearest spot)', () => {
    render(<ChainTable contracts={[C(95, 'CALL', 0.2), C(100, 'CALL', 0.2)]} spot={101} />)
    expect(screen.getByTestId('chain-row-100')).toHaveAttribute('data-atm', 'true')
    expect(screen.getByTestId('chain-row-95')).not.toHaveAttribute('data-atm', 'true')
  })

  it('shows an empty message when there are no contracts', () => {
    render(<ChainTable contracts={[]} spot={100} />)
    expect(screen.getByTestId('chain-empty')).toBeInTheDocument()
  })
})
