import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BacktestStatus } from './BacktestStatus'

describe('BacktestStatus', () => {
  it('shows a running state with the estimate', () => {
    render(<BacktestStatus status="running" estSeconds={15} error={null} />)
    expect(screen.getByTestId('bt-running').textContent).toMatch(/15/)
  })
  it('shows the failure message', () => {
    render(<BacktestStatus status="failed" estSeconds={0} error="no bars for SPY" />)
    expect(screen.getByTestId('bt-error').textContent).toContain('no bars for SPY')
  })
})
