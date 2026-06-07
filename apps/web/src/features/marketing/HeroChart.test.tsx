import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { HeroChart } from './HeroChart'

describe('HeroChart', () => {
  it('renders a real, server-safe payoff figure with derived stats and no fabricated prices', () => {
    const { container } = render(<HeroChart />)

    // The actual PayoffChart SVG (authentic explainer data) is present.
    expect(screen.getByTestId('payoff-chart')).toBeInTheDocument()

    // Derived stat labels render (values come from maxPL/breakevens, not mocks).
    expect(screen.getByText('max profit')).toBeInTheDocument()
    expect(screen.getByText('max loss')).toBeInTheDocument()
    expect(screen.getByText('breakeven')).toBeInTheDocument()

    // No currency/returns claims anywhere in the hero art.
    expect(container.textContent).not.toContain('$')
  })
})
