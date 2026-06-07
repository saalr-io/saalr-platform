import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { GettingStarted } from './GettingStarted'
import * as ob from '../../lib/onboarding'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>
}

describe('GettingStarted', () => {
  beforeEach(() => { localStorage.clear(); vi.restoreAllMocks() })

  it('shows the 4 steps with one completed', async () => {
    vi.spyOn(ob, 'getOnboarding').mockResolvedValue({ steps: ['build_strategy'], all_done: false })
    render(wrap(<GettingStarted />))
    expect(await screen.findByTestId('getting-started')).toBeInTheDocument()
    expect(screen.getAllByTestId(/^ob-step-/)).toHaveLength(4)
  })

  it('hides when all_done', async () => {
    vi.spyOn(ob, 'getOnboarding').mockResolvedValue({ steps: [...ob.ONBOARDING_STEPS], all_done: true })
    render(wrap(<GettingStarted />))
    await waitFor(() => expect(screen.queryByTestId('getting-started')).toBeNull())
  })

  it('hides after dismiss', async () => {
    vi.spyOn(ob, 'getOnboarding').mockResolvedValue({ steps: [], all_done: false })
    render(wrap(<GettingStarted />))
    fireEvent.click(await screen.findByTestId('ob-dismiss'))
    await waitFor(() => expect(screen.queryByTestId('getting-started')).toBeNull())
  })
})
