import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Tiers } from './Tiers'

describe('Tiers', () => {
  it('shows the three plans and a free CTA into the app', () => {
    render(<Tiers />)
    expect(screen.getByRole('heading', { name: 'Free' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Pro' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Premium' })).toBeInTheDocument()

    const cta = screen.getByRole('link', { name: /Start free/ })
    expect(cta).toHaveAttribute('href', '/app')
  })

  it('shows no dollar prices', () => {
    const { container } = render(<Tiers />)
    expect(container.textContent).not.toContain('$')
  })
})
