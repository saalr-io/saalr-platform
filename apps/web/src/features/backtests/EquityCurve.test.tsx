import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { EquityCurve } from './EquityCurve'

const series = [
  { date: '2023-01-03', equity: 100000 },
  { date: '2023-01-04', equity: 101000 },
  { date: '2023-01-05', equity: 99000 },
]

describe('EquityCurve', () => {
  it('draws one point per equity sample plus a baseline', () => {
    render(<EquityCurve series={series} initialCapital={100000} />)
    expect(screen.getByTestId('equity-line').getAttribute('points')!.trim().split(' ')).toHaveLength(3)
    expect(screen.getByTestId('equity-baseline')).toBeInTheDocument()
  })

  it('labels the equity and date axes', () => {
    render(<EquityCurve series={series} initialCapital={100000} />)
    const fig = screen.getByTestId('equity-curve')
    expect(fig.textContent).toContain('equity')      // y-axis title
    expect(fig.textContent).toContain('date')        // x-axis title
    expect(fig.textContent).toContain('$100k')       // initial-capital tick
    expect(fig.textContent).toContain('2023-01-03')  // first date tick
  })
})
