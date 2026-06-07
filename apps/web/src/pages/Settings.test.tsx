import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { Settings } from './Settings'

vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({
    me: {
      user: { id: '1', email: 'a@b.com' },
      tenant: { id: 't1', display_name: 'Acme', country_code: 'US' },
      tier: 'pro',
      entitlements: {},
      marketing_opt_in: false,
      preferred_tz: 'UTC',
      preferred_locale: 'en-US',
      deletion_requested: false,
    },
    refresh: vi.fn(),
    status: 'authed',
  }),
}))

vi.mock('../features/billing/hooks', () => ({
  usePortal: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('../features/account/hooks', () => ({
  useOptIn: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateProfile: () => ({ mutate: vi.fn(), isPending: false }),
  useRequestDeletion: () => ({ mutate: vi.fn(), isPending: false, isSuccess: false }),
}))

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe('Settings page', () => {
  beforeEach(() => { vi.restoreAllMocks() })

  it('renders email and tier in Account section', () => {
    render(wrap(<Settings />))
    expect(screen.getByText('a@b.com')).toBeInTheDocument()
    expect(screen.getByText('pro')).toBeInTheDocument()
  })

  it('renders the marketing opt-in toggle', () => {
    render(wrap(<Settings />))
    expect(screen.getByTestId('optin-toggle')).toBeInTheDocument()
  })

  it('renders the timezone input in Profile section', () => {
    render(wrap(<Settings />))
    const tzInput = screen.getByTestId('tz-input')
    expect(tzInput).toBeInTheDocument()
    expect((tzInput as HTMLInputElement).value).toBe('UTC')
  })

  it('renders delete button disabled until confirm input equals DELETE', () => {
    render(wrap(<Settings />))
    const btn = screen.getByTestId('delete-request-btn')
    expect(btn).toBeDisabled()

    const input = screen.getByTestId('delete-confirm-input')
    fireEvent.change(input, { target: { value: 'DELET' } })
    expect(btn).toBeDisabled()

    fireEvent.change(input, { target: { value: 'DELETE' } })
    expect(btn).not.toBeDisabled()
  })
})
