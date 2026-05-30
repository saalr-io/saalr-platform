import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { LegEditor } from './LegEditor'
import type { StrategyConfig } from '../../lib/strategies'

const cfg: StrategyConfig = {
  underlying: 'AAPL',
  legs: [{ kind: 'option', option_type: 'CALL', side: 'BUY', strike: 100, expiry: '2026-12-18', qty: 1, entry_price: 6 }],
}

describe('LegEditor', () => {
  it('adds a leg', () => {
    const onChange = vi.fn()
    render(<LegEditor config={cfg} onChange={onChange} />)
    fireEvent.click(screen.getByTestId('add-leg'))
    expect(onChange).toHaveBeenCalled()
    const next = onChange.mock.calls.at(-1)![0] as StrategyConfig
    expect(next.legs).toHaveLength(2)
  })

  it('removes a leg', () => {
    const onChange = vi.fn()
    render(<LegEditor config={cfg} onChange={onChange} />)
    fireEvent.click(screen.getByTestId('remove-leg-0'))
    expect((onChange.mock.calls.at(-1)![0] as StrategyConfig).legs).toHaveLength(0)
  })

  it('edits the strike of a leg', () => {
    const onChange = vi.fn()
    render(<LegEditor config={cfg} onChange={onChange} />)
    fireEvent.change(screen.getByTestId('strike-0'), { target: { value: '105' } })
    const leg = (onChange.mock.calls.at(-1)![0] as StrategyConfig).legs[0]
    expect(leg.kind === 'option' && leg.strike).toBe(105)
  })

  it('edits the underlying', () => {
    const onChange = vi.fn()
    render(<LegEditor config={cfg} onChange={onChange} />)
    fireEvent.change(screen.getByTestId('underlying'), { target: { value: 'TSLA' } })
    expect((onChange.mock.calls.at(-1)![0] as StrategyConfig).underlying).toBe('TSLA')
  })
})
