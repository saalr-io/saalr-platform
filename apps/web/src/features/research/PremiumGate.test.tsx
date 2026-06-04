import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { PremiumGate } from './PremiumGate'

describe('PremiumGate', () => {
  it('links to the billing page to upgrade to Premium', () => {
    render(<MemoryRouter><PremiumGate /></MemoryRouter>)
    const link = screen.getByRole('link', { name: /upgrade to premium/i })
    expect(link).toHaveAttribute('href', '/billing?plan=premium')
  })
})
