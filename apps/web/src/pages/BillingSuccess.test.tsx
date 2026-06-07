import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import * as billing from '../lib/billing'
import { BillingSuccess } from './BillingSuccess'

const refresh = vi.fn(async () => {})
let mockMe: { tier: string } | undefined
vi.mock('../auth/AuthContext', () => ({ useAuth: () => ({ refresh, me: mockMe }) }))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

const SUB = (tier: string) => ({
  tier, status: 'active', current_period_end: null,
  cancel_at_period_end: false, entitlements: {}, has_customer: true,
})

describe('BillingSuccess', () => {
  beforeEach(() => { vi.restoreAllMocks(); refresh.mockClear(); mockMe = undefined })

  it('confirms once the tier flips and refreshes the session', async () => {
    const get = vi.spyOn(billing, 'getSubscription')
      .mockResolvedValueOnce(SUB('free') as never)
      .mockResolvedValue(SUB('pro') as never)
    render(wrap(<BillingSuccess />))
    await waitFor(() => expect(screen.getByTestId('billing-confirmed').textContent).toMatch(/pro/i),
      { timeout: 5000 })
    expect(refresh).toHaveBeenCalled()
    expect(get).toHaveBeenCalled()
  })

  it('confirms a pro→premium upgrade only when the tier changes from the mount tier', async () => {
    mockMe = { tier: 'pro' }  // already on Pro before this checkout
    vi.spyOn(billing, 'getSubscription')
      .mockResolvedValueOnce(SUB('pro') as never)   // still pro — must NOT confirm
      .mockResolvedValue(SUB('premium') as never)   // flipped to premium
    render(wrap(<BillingSuccess />))
    await waitFor(() => expect(screen.getByTestId('billing-confirmed').textContent).toMatch(/premium/i),
      { timeout: 5000 })
    expect(refresh).toHaveBeenCalled()
  })
})
