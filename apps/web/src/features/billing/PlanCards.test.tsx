import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import * as billing from '../../lib/billing'
import { PlanCards } from './PlanCards'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}

describe('PlanCards', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('marks the current tier and offers upgrades for higher tiers', () => {
    render(wrap(<PlanCards current="free" />))
    expect(screen.getByTestId('plan-free').textContent).toContain('Current plan')
    expect(screen.getByTestId('plan-pro').querySelector('button')!.textContent).toContain('Upgrade')
    expect(screen.getByTestId('plan-premium').querySelector('button')!.textContent).toContain('Upgrade')
  })

  it('upgrading calls the client then redirects', async () => {
    vi.spyOn(billing, 'startUpgrade').mockResolvedValue({ checkout_url: 'https://stripe/c/x' })
    const redirect = vi.spyOn(billing, 'redirectTo').mockImplementation(() => {})
    render(wrap(<PlanCards current="free" />))
    fireEvent.click(screen.getByTestId('plan-pro').querySelector('button')!)
    await waitFor(() => expect(billing.startUpgrade).toHaveBeenCalledWith('pro', 'monthly'))
    await waitFor(() => expect(redirect).toHaveBeenCalledWith('https://stripe/c/x'))
  })

  it('defaults to monthly and upgrades monthly', async () => {
    const spy = vi.spyOn(billing, 'startUpgrade').mockResolvedValue({ checkout_url: 'x' })
    vi.spyOn(billing, 'redirectTo').mockImplementation(() => {})
    render(wrap(<PlanCards current="free" />))
    fireEvent.click(screen.getByRole('button', { name: /Upgrade to Pro/i }))
    await waitFor(() => expect(spy).toHaveBeenCalledWith('pro', 'monthly'))
  })

  it('annual toggle shows the discount badge and upgrades annually', async () => {
    const spy = vi.spyOn(billing, 'startUpgrade').mockResolvedValue({ checkout_url: 'x' })
    vi.spyOn(billing, 'redirectTo').mockImplementation(() => {})
    render(wrap(<PlanCards current="free" />))
    fireEvent.click(screen.getByTestId('billing-interval-annual'))
    expect(screen.getAllByTestId('annual-badge').length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('button', { name: /Upgrade to Premium/i }))
    await waitFor(() => expect(spy).toHaveBeenCalledWith('premium', 'annual'))
  })

  it('a Pro user sees Pro as current and only Premium upgradeable', () => {
    render(wrap(<PlanCards current="pro" />))
    expect(screen.getByTestId('plan-pro').textContent).toContain('Current plan')
    expect(screen.queryByTestId('plan-free')!.querySelector('button')).toBeNull()
    expect(screen.getByTestId('plan-premium').querySelector('button')!.textContent).toContain('Upgrade')
  })
})
