import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PremiumGate } from './PremiumGate'

describe('PremiumGate', () => {
  it('renders the premium gate panel', () => {
    render(<PremiumGate />)
    expect(screen.getByTestId('premium-gate')).toBeInTheDocument()
    expect(screen.getByTestId('premium-gate').textContent).toContain('Premium feature')
    expect(screen.getByTestId('premium-gate').textContent).toContain('Research notes are a Premium feature')
  })
})
