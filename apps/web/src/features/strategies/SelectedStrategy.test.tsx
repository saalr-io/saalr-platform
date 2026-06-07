import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SelectedStrategy } from './SelectedStrategy'
import type { StrategyConfig } from '../../lib/strategies'

const CONFIG: StrategyConfig = {
  underlying: 'SPY',
  legs: [
    { kind: 'option', option_type: 'CALL', side: 'BUY', strike: 580, expiry: '2026-12-18', qty: 1 },
    { kind: 'option', option_type: 'CALL', side: 'SELL', strike: 600, expiry: '2026-12-18', qty: 1 },
  ],
}

describe('SelectedStrategy', () => {
  it('shows the underlying and each leg', () => {
    render(<SelectedStrategy config={CONFIG} onChange={() => {}} />)
    expect(screen.getByTestId('mc-selected').textContent).toContain('SPY')
    expect(screen.getAllByTestId(/^mc-leg-/)).toHaveLength(2)
    const leg0 = screen.getByTestId('mc-leg-0')
    expect(leg0.textContent).toContain('BUY')
    expect(leg0.textContent).toContain('CALL')
    expect(leg0.textContent).toContain('580')
    expect(screen.getByTestId('mc-leg-1').textContent).toContain('SELL')
  })

  it('fires onChange from the Change button', () => {
    const onChange = vi.fn()
    render(<SelectedStrategy config={CONFIG} onChange={onChange} />)
    fireEvent.click(screen.getByTestId('mc-change'))
    expect(onChange).toHaveBeenCalled()
  })

  it('omits the Change button when onChange is not given', () => {
    render(<SelectedStrategy config={CONFIG} />)
    expect(screen.queryByTestId('mc-change')).toBeNull()
    expect(screen.getAllByTestId(/^mc-leg-/)).toHaveLength(2)
  })
})
