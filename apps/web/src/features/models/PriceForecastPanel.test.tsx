import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PriceForecastPanel } from './PriceForecastPanel'
import type { PriceForecast } from '../../lib/models'

const FC: PriceForecast = {
  ticker: 'AAPL', market: 'US', as_of: '2026-06-06T00:00:00Z',
  horizon_days: 5, last_close: 100, primary_model: 'naive',
  models: [
    { model: 'arima', path: [101, 102, 102, 103, 103], ci_95: [[99, 103], [98, 106], [98, 107], [97, 109], [96, 110]],
      expected_return_pct: 3, direction: 'up', holdout_mae: 2.1, directional_accuracy: 0.55 },
    { model: 'lstm', path: [100, 99, 99, 98, 98], ci_95: [[98, 102], [96, 102], [95, 103], [94, 103], [93, 103]],
      expected_return_pct: -2, direction: 'down', holdout_mae: 2.6, directional_accuracy: 0.5 },
    { model: 'naive', path: [100.1, 100.2, 100.3, 100.4, 100.5], ci_95: null,
      expected_return_pct: 0.5, direction: 'flat', holdout_mae: 1.9, directional_accuracy: 0.52 },
  ],
  validation: { holdout_days: 60, n_origins: 5, best_model: 'naive' },
  approximate: true, disclaimer: 'Educational. Daily price direction is near-random; the naive baseline often wins.',
}

describe('PriceForecastPanel', () => {
  it('renders a line per model, axes, the primary badge and disclaimer', () => {
    render(<PriceForecastPanel forecast={FC} />)
    expect(screen.getByTestId('price-forecast-panel')).toBeInTheDocument()
    expect(screen.getAllByTestId('pf-line')).toHaveLength(3)
    expect(screen.getByTestId('pf-primary')).toHaveTextContent('naive')
    expect(screen.getByTestId('pf-axis-x')).toBeInTheDocument()
    expect(screen.getByTestId('pf-axis-y')).toBeInTheDocument()
    expect(screen.getByTestId('pf-disclaimer')).toBeInTheDocument()
  })
})
