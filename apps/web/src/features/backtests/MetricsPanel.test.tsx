import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MetricsPanel } from './MetricsPanel'
import type { BacktestMetrics } from '../../lib/backtests'

const m: BacktestMetrics = {
  total_return: 0.124, annualized_return: 0.061, sharpe: 0.67, sortino: 0.9,
  max_drawdown: 0.18, win_rate: 0.55, trades: 12, avg_trade_pnl: 340.5,
}

describe('MetricsPanel', () => {
  it('renders metrics with percent formatting + the approximate chip', () => {
    render(<MetricsPanel metrics={m} finalEquity={112400} approximate model="bsm" volLookback={20} />)
    expect(screen.getByTestId('mx-total-return').textContent).toContain('12.4%')
    expect(screen.getByTestId('mx-sharpe').textContent).toContain('0.67')
    expect(screen.getByText(/approximate/i)).toBeInTheDocument()
  })
})
