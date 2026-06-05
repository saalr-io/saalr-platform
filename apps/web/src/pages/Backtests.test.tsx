import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import * as strategies from '../lib/strategies'
import * as backtests from '../lib/backtests'
import { Backtests } from './Backtests'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>
}

const STRAT = { strategy_id: 's1', name: 'SPY bull call', description: null, state: 'draft', market: 'US', config: { underlying: 'SPY', legs: [] }, created_at: 'x', updated_at: 'x' }

describe('Backtests page', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('prompts when there are no saved strategies', async () => {
    vi.spyOn(strategies, 'listStrategies').mockResolvedValue({ strategies: [], next_cursor: null })
    render(wrap(<Backtests />))
    await waitFor(() => expect(screen.getByTestId('no-strategies')).toBeInTheDocument())
  })

  it('runs a backtest and renders the curve + metrics on success', async () => {
    vi.spyOn(strategies, 'listStrategies').mockResolvedValue({ strategies: [STRAT] as never, next_cursor: null })
    vi.spyOn(backtests, 'createBacktest').mockResolvedValue({ backtest_id: 'b1', status: 'queued', estimated_duration_seconds: 10, poll_url: '/v1/backtests/b1' })
    vi.spyOn(backtests, 'getBacktest').mockResolvedValue({
      backtest_id: 'b1', status: 'succeeded',
      metrics: { total_return: 0.1, annualized_return: 0.05, sharpe: 0.6, sortino: 0.8, max_drawdown: 0.2, win_rate: 0.5, trades: 8, avg_trade_pnl: 100 },
      equity_series: [{ date: '2023-01-03', equity: 100000 }, { date: '2023-01-04', equity: 110000 }],
    })
    render(wrap(<Backtests />))
    await waitFor(() => expect(screen.getByTestId('bt-strategy')).toBeInTheDocument())
    fireEvent.change(screen.getByTestId('bt-strategy'), { target: { value: 's1' } })
    fireEvent.click(screen.getByTestId('bt-run'))
    await waitFor(() => expect(screen.getByTestId('equity-curve')).toBeInTheDocument())
    expect(screen.getByTestId('metrics-panel')).toBeInTheDocument()
    expect(screen.getByTestId('mx-total-return').textContent).toContain('10.0%')
  })
})
