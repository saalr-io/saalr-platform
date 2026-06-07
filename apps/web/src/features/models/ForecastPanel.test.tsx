import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ForecastPanel } from './ForecastPanel'
import type { VolForecast } from '../../lib/models'

const base: VolForecast = {
  horizon_days: 3,
  primary_model: 'garch',
  primary_forecast: [20, 21, 22],
  primary_ci_95: [[18, 22], [19, 23], [20, 24]],
  alternative_models: [{ model: 'hv21', forecast: [19, 19, 19], status: 'baseline', delta_mae_vs_baseline: -0.1 }],
  validation: { holdout_days: 40, garch_mae: 0.5, hv21_mae: 0.6, har_mae: 0.45, lift: 0.1 },
  model: 'garch(1,1)', iv_source: 'realized_returns', approximate: true,
  params: { omega: 0.0001, alpha: 0.08, beta: 0.9 },
}

describe('ForecastPanel', () => {
  it('draws a primary line with one point per horizon day and a CI band', () => {
    render(<ForecastPanel forecast={base} />)
    expect(screen.getByTestId('forecast-line').getAttribute('points')!.trim().split(' ')).toHaveLength(3)
    expect(screen.getByTestId('forecast-ci')).toBeInTheDocument()
    expect(screen.getByTestId('forecast-primary').textContent).toContain('garch')
    expect(screen.getByText('approximate')).toBeInTheDocument()
  })

  it('omits the CI band when primary_ci_95 is null (hv21 primary)', () => {
    render(<ForecastPanel forecast={{ ...base, primary_model: 'hv21', primary_ci_95: null }} />)
    expect(screen.queryByTestId('forecast-ci')).toBeNull()
    expect(screen.getByTestId('forecast-line')).toBeInTheDocument()
  })

  it('hides the approximate tag when approximate is false', () => {
    render(<ForecastPanel forecast={{ ...base, approximate: false }} />)
    expect(screen.queryByText('approximate')).toBeNull()
  })
})

const HAR_PRIMARY: VolForecast = {
  horizon_days: 5, primary_model: 'har', primary_forecast: [20, 21, 21, 22, 22], primary_ci_95: null,
  alternative_models: [
    { model: 'garch', forecast: [19, 20, 20, 21, 21], status: 'outperforms_baseline', delta_mae_vs_baseline: -0.1 },
    { model: 'hv21', forecast: [23, 23, 23, 23, 23], status: 'baseline', delta_mae_vs_baseline: 0 },
  ],
  validation: { holdout_days: 60, garch_mae: 0.4, hv21_mae: 0.5, har_mae: 0.3, lift: 0.2 },
  model: 'garch(1,1)', iv_source: 'realized_returns', approximate: true,
  params: { omega: 0.0001, alpha: 0.1, beta: 0.85 },
}

describe('ForecastPanel HAR', () => {
  it('shows har as primary, both alternatives, and the har MAE row', () => {
    render(<ForecastPanel forecast={HAR_PRIMARY} />)
    expect(screen.getByTestId('forecast-primary')).toHaveTextContent('har')
    expect(screen.getAllByTestId('forecast-alt')).toHaveLength(2)
    expect(screen.getByText(/har MAE/i)).toBeInTheDocument()
  })
})
