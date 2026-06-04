import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import * as billing from '../../lib/billing'
import { useUpgrade } from './hooks'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}

function UpgradeProbe() {
  const up = useUpgrade()
  return <button onClick={() => up.mutate('pro')}>go</button>
}

describe('billing hooks', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('useUpgrade redirects to the checkout url', async () => {
    vi.spyOn(billing, 'startUpgrade').mockResolvedValue({ checkout_url: 'https://stripe/c/9' })
    const redirect = vi.spyOn(billing, 'redirectTo').mockImplementation(() => {})
    render(wrap(<UpgradeProbe />))
    fireEvent.click(screen.getByText('go'))
    await waitFor(() => expect(redirect).toHaveBeenCalledWith('https://stripe/c/9'))
  })
})
