import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { UpgradeHint } from './UpgradeHint'

describe('UpgradeHint', () => {
  it('renders the feature text and an upgrade link to the chosen plan', () => {
    render(<MemoryRouter><UpgradeHint feature="Forecasts for your holdings" plan="premium" /></MemoryRouter>)
    expect(screen.getByTestId('upgrade-hint').textContent).toContain('Forecasts for your holdings')
    expect(screen.getByRole('link', { name: /upgrade/i }).getAttribute('href')).toBe('/billing?plan=premium')
  })

  it('defaults to the pro plan', () => {
    render(<MemoryRouter><UpgradeHint feature="x" /></MemoryRouter>)
    expect(screen.getByRole('link', { name: /upgrade/i }).getAttribute('href')).toBe('/billing?plan=pro')
  })
})
