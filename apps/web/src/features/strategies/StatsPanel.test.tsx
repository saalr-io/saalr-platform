import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatsPanel } from './StatsPanel'
import type { AnalyzeResult } from '../../lib/strategies'

const base: AnalyzeResult = {
  expiration_curve: [], breakevens: [104], max_profit: 600, max_loss: -400,
  unbounded_profit: false, unbounded_loss: false, net_premium: 400, risk_reward: 1.5,
}

describe('StatsPanel', () => {
  it('shows Unbounded when the flag is set', () => {
    render(<StatsPanel result={{ ...base, max_profit: null, unbounded_profit: true }} />)
    expect(screen.getByTestId('stat-max-profit')).toHaveTextContent('Unbounded')
  })

  it('hides live-only stats and shows upgrade hint when absent', () => {
    render(<StatsPanel result={base} />)
    expect(screen.queryByTestId('stat-greeks')).not.toBeInTheDocument()
    expect(screen.getByTestId('upgrade-hint')).toBeInTheDocument()
  })

  it('shows greeks + POP when present', () => {
    render(<StatsPanel result={{ ...base,
      net_greeks: { delta: 12, gamma: 1, theta: -5, vega: 8, rho: 0 },
      probability_of_profit: { pop: 0.58, method: 'lognormal_atm_iv', approximate: true } }} />)
    expect(screen.getByTestId('stat-greeks')).toBeInTheDocument()
    expect(screen.getByTestId('stat-pop')).toHaveTextContent('58')
  })
})
