import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Research } from './Research'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}

describe('Research page', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('shows premium gate when notes list returns premium 402', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({ detail: { error: { code: 'ENTITLEMENT_RESEARCH_AGENT_REQUIRES_PREMIUM' } } }),
        { status: 402 },
      ),
    ))
    render(wrap(<Research />))
    await waitFor(() => expect(screen.getByTestId('premium-gate')).toBeInTheDocument())
  })

  it('shows the run form and empty hint when notes load successfully', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ notes: [], next_cursor: null }), { status: 200 }),
    ))
    render(wrap(<Research />))
    await waitFor(() => expect(screen.getByTestId('run-form')).toBeInTheDocument())
    expect(screen.getByTestId('empty-hint')).toBeInTheDocument()
  })

  it('shows premium gate when onPremiumRequired fires from RunForm', async () => {
    // First call (listNotes) succeeds; second call (runResearch) returns premium 402
    let callCount = 0
    vi.stubGlobal('fetch', vi.fn(async () => {
      callCount++
      if (callCount === 1) {
        return new Response(JSON.stringify({ notes: [], next_cursor: null }), { status: 200 })
      }
      return new Response(
        JSON.stringify({ detail: { error: { code: 'ENTITLEMENT_RESEARCH_AGENT_REQUIRES_PREMIUM' } } }),
        { status: 402 },
      )
    }))
    render(wrap(<Research />))
    await waitFor(() => expect(screen.getByTestId('run-form')).toBeInTheDocument())

    const input = screen.getByTestId('ticker-input')
    const btn = screen.getByTestId('run-btn')
    // Use fireEvent from @testing-library/react
    const { fireEvent } = await import('@testing-library/react')
    fireEvent.change(input, { target: { value: 'AAPL' } })
    fireEvent.click(btn)

    await waitFor(() => expect(screen.getByTestId('premium-gate')).toBeInTheDocument())
  })
})
