import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { ChainTable } from './ChainTable'
import type { Contract, Greeks } from '../../lib/market'

const G = (iv: number): Greeks => ({ price: 1, delta: 0.5, gamma: 0.01, theta: -0.02, vega: 0.1, rho: 0.05, iv })
const C = (strike: number, type: 'CALL' | 'PUT', iv: number, oi = 99): Contract => ({
  expiry: '2026-12-18', strike, type, bid: 1, ask: 1.2, last: 1.1, volume: 10, open_interest: oi,
  ours: G(iv), vendor: { iv: iv - 0.001, delta: 0.5, gamma: 0.01, theta: -0.02, vega: 0.1 },
})

// a strike ladder straddling spot=101, with a call+put at each strike
function ladder(strikes: number[], spot: number) {
  const cs = strikes.flatMap((k) => [C(k, 'CALL', 0.2, k), C(k, 'PUT', 0.25, k)])
  return <ChainTable contracts={cs} spot={spot} />
}

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

  it('tints the ITM side: calls below spot, puts above spot', () => {
    render(ladder([95, 100, 105], 101))
    // strike 95 < spot -> call side ITM
    expect(within(screen.getByTestId('chain-row-95')).getByTestId('call-cells-95')).toHaveAttribute('data-itm', 'true')
    expect(within(screen.getByTestId('chain-row-95')).getByTestId('put-cells-95')).not.toHaveAttribute('data-itm', 'true')
    // strike 105 > spot -> put side ITM
    expect(within(screen.getByTestId('chain-row-105')).getByTestId('put-cells-105')).toHaveAttribute('data-itm', 'true')
    expect(within(screen.getByTestId('chain-row-105')).getByTestId('call-cells-105')).not.toHaveAttribute('data-itm', 'true')
  })

  it('toggles between prices and greeks columns', () => {
    // headers are mirrored (calls + puts), so each label appears twice -> use *AllByText
    render(ladder([100, 101, 102], 101))
    expect(screen.getAllByText('OI').length).toBeGreaterThan(0)
    expect(screen.queryAllByText('Δ')).toHaveLength(0)
    fireEvent.click(screen.getByTestId('chain-greeks-toggle'))
    expect(screen.getAllByText('Δ').length).toBeGreaterThan(0)
    expect(screen.queryAllByText('OI')).toHaveLength(0)
  })

  it('limits to a window around ATM by default and expands on All', () => {
    const strikes = Array.from({ length: 41 }, (_, i) => 80 + i) // 80..120, ATM=101
    render(ladder(strikes, 101))
    // default window = 10 each side -> at most 21 strike rows
    expect(screen.queryByTestId('chain-row-80')).not.toBeInTheDocument()
    expect(screen.getByTestId('chain-row-101')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('chain-window-all'))
    expect(screen.getByTestId('chain-row-80')).toBeInTheDocument()
  })

  it('renders a spot line and an OI bar', () => {
    render(ladder([100, 101, 102], 101))
    expect(screen.getByTestId('chain-spot-line').textContent).toContain('101')
    expect(screen.getByTestId('oi-bar-call-101')).toBeInTheDocument()
  })

  it('shows the Chg OI column and switches values by window', () => {
    const c: Contract = {
      ...C(180, 'CALL', 0.26, 500),
      oi_change: { day: 12400, '1h': -2100, '3h': 0, '4h': 500 },
    }
    render(<ChainTable contracts={[c]} spot={185}
      oiBaselines={{ day: { ts: '2026-05-30T10:00:00+00:00', elapsed_label: '~4h30m' },
        '1h': null, '3h': null, '4h': null }} />)
    const cell = screen.getByTestId('chg-call-180')
    expect(cell.textContent).toContain('+12.4k')
    expect(cell.className).toContain('text-pos')
    expect(screen.getByTestId('oi-baseline-note').textContent).toContain('~4h30m')
    fireEvent.click(screen.getByTestId('oi-window-1h'))
    expect(screen.getByTestId('chg-call-180').textContent).toContain('-2.1k')
    expect(screen.getByTestId('chg-call-180').className).toContain('text-neg')
  })

  it('renders an em-dash and a no-baseline note when oi_change is missing', () => {
    render(<ChainTable contracts={[C(180, 'CALL', 0.26, 500)]} spot={185}
      oiBaselines={{ day: null, '1h': null, '3h': null, '4h': null }} />)
    expect(screen.getByTestId('chg-call-180').textContent).toContain('—')
    expect((screen.getByTestId('oi-baseline-note').textContent ?? '').toLowerCase())
      .toContain('no earlier snapshot')
  })
})
