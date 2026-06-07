import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import * as billing from '../lib/billing'
import { Billing } from './Billing'

function wrap(ui: React.ReactNode, path = '/billing') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

const SUB = (over = {}) => ({
  tier: 'free', status: 'active', current_period_end: null,
  cancel_at_period_end: false, entitlements: {}, has_customer: false, ...over,
})

describe('Billing page', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('shows the current plan and no manage button without a customer', async () => {
    vi.spyOn(billing, 'getSubscription').mockResolvedValue(SUB() as never)
    render(wrap(<Billing />))
    await waitFor(() => expect(screen.getByTestId('current-plan').textContent).toMatch(/free/i))
    expect(screen.queryByTestId('manage-billing')).toBeNull()
  })

  it('shows Manage billing when a customer exists and opens the portal', async () => {
    vi.spyOn(billing, 'getSubscription').mockResolvedValue(
      SUB({ tier: 'pro', status: 'active', has_customer: true }) as never)
    vi.spyOn(billing, 'openPortal').mockResolvedValue({ portal_url: 'https://stripe/p/2' })
    const redirect = vi.spyOn(billing, 'redirectTo').mockImplementation(() => {})
    render(wrap(<Billing />))
    const btn = await screen.findByTestId('manage-billing')
    fireEvent.click(btn)
    await waitFor(() => expect(redirect).toHaveBeenCalledWith('https://stripe/p/2'))
  })
})
