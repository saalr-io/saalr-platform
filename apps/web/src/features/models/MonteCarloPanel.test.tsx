import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MonteCarloPanel } from './MonteCarloPanel'
import type { MonteCarloResult } from '../../lib/models'

const R = (over: Partial<MonteCarloResult> = {}): MonteCarloResult => ({
  pop: 0.62, ev: 35.5, paths: 10000,
  histogram: { counts: [2, 5, 9, 4], bin_edges: [-100, -50, 0, 50, 100] },
  percentiles: { p5: -80, p50: 10, p95: 90 },
  max_profit_observed: 120, max_loss_observed: -110,
  model: 'gbm_mc', approximate: true, seed: 0,
  underlying: 'SPY', market: 'US', spot: 500, sigma: 0.2, sigma_source: 'garch',
  horizon_days: 14, rate: 0.04,
  sentiment: { applied: false, reason: 'not_requested' }, ...over,
})

describe('MonteCarloPanel', () => {
  it('renders POP, EV, percentiles and one bar per histogram bin', () => {
    render(<MonteCarloPanel result={R()} />)
    expect(screen.getByTestId('mc-pop').textContent).toContain('62.0%')
    expect(screen.getByTestId('mc-ev').textContent).toContain('35.5')
    expect(screen.getAllByTestId('mc-bar')).toHaveLength(4)
    expect(screen.getByTestId('mc-sigma-source').textContent).toContain('garch')
  })

  it('notes when sentiment was applied', () => {
    render(<MonteCarloPanel result={R({ sentiment: { applied: true, score: 0.4, label: 'bullish' } })} />)
    expect(screen.getByTestId('mc-sentiment').textContent).toContain('sentiment applied')
    expect(screen.getByTestId('mc-sentiment').textContent).toContain('bullish')
  })

  it('renders without bars for an empty histogram', () => {
    render(<MonteCarloPanel result={R({ histogram: { counts: [], bin_edges: [0] } })} />)
    expect(screen.getByTestId('mc-panel')).toBeInTheDocument()
    expect(screen.queryAllByTestId('mc-bar')).toHaveLength(0)
  })
})
