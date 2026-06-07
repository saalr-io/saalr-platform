import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RunForm } from './RunForm'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}

const SUCCEEDED_NOTE = {
  note_id: 'n1', ticker: 'AAPL', market: 'US',
  summary: '## Overview\nSolid.', signals: { spot: 192.5, vol_forecast: null, sentiment: null },
  sources: [], model: 'claude-3-opus', usage: { prompt_tokens: 100, completion_tokens: 50 },
  cost_usd: 0.01, status: 'succeeded' as const, created_at: '2026-06-03T10:00:00Z',
}

describe('RunForm', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('200 path calls onNote with the full note', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify(SUCCEEDED_NOTE), { status: 200 }),
    ))
    const onNote = vi.fn()
    const onPending = vi.fn()
    const onPremiumRequired = vi.fn()
    render(wrap(<RunForm onNote={onNote} onPending={onPending} onPremiumRequired={onPremiumRequired} />))

    fireEvent.change(screen.getByTestId('ticker-input'), { target: { value: 'AAPL' } })
    fireEvent.click(screen.getByTestId('run-btn'))

    await waitFor(() => expect(onNote).toHaveBeenCalledWith(expect.objectContaining({ ticker: 'AAPL', status: 'succeeded' })))
    expect(onPending).not.toHaveBeenCalled()
  })

  it('202 path calls onPending with the note_id', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ note_id: 'n2', status: 'queued', poll_url: '/research/notes/n2' }), { status: 202 }),
    ))
    const onNote = vi.fn()
    const onPending = vi.fn()
    const onPremiumRequired = vi.fn()
    render(wrap(<RunForm onNote={onNote} onPending={onPending} onPremiumRequired={onPremiumRequired} />))

    fireEvent.change(screen.getByTestId('ticker-input'), { target: { value: 'TSLA' } })
    fireEvent.click(screen.getByTestId('run-btn'))

    await waitFor(() => expect(onPending).toHaveBeenCalledWith('n2'))
    expect(onNote).not.toHaveBeenCalled()
  })

  it('budget 402 shows monthly budget message', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({ detail: { error: { code: 'RESEARCH_BUDGET_EXCEEDED' } } }),
        { status: 402 },
      ),
    ))
    const onNote = vi.fn()
    const onPending = vi.fn()
    const onPremiumRequired = vi.fn()
    render(wrap(<RunForm onNote={onNote} onPending={onPending} onPremiumRequired={onPremiumRequired} />))

    fireEvent.change(screen.getByTestId('ticker-input'), { target: { value: 'MSFT' } })
    fireEvent.click(screen.getByTestId('run-btn'))

    await waitFor(() => expect(screen.getByTestId('run-error')).toBeInTheDocument())
    expect(screen.getByTestId('run-error').textContent).toContain('Monthly research budget reached')
  })

  it('429 shows daily limit message', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({ detail: { error: { code: 'RATE_LIMIT_RESEARCH_DAILY_EXCEEDED' } } }),
        { status: 429 },
      ),
    ))
    render(wrap(<RunForm onNote={vi.fn()} onPending={vi.fn()} onPremiumRequired={vi.fn()} />))

    fireEvent.change(screen.getByTestId('ticker-input'), { target: { value: 'GOOGL' } })
    fireEvent.click(screen.getByTestId('run-btn'))

    await waitFor(() => expect(screen.getByTestId('run-error')).toBeInTheDocument())
    expect(screen.getByTestId('run-error').textContent).toContain('Daily limit of 10')
  })

  it('premium 402 calls onPremiumRequired and shows no inline error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({ detail: { error: { code: 'ENTITLEMENT_RESEARCH_AGENT_REQUIRES_PREMIUM' } } }),
        { status: 402 },
      ),
    ))
    const onPremiumRequired = vi.fn()
    render(wrap(<RunForm onNote={vi.fn()} onPending={vi.fn()} onPremiumRequired={onPremiumRequired} />))

    fireEvent.change(screen.getByTestId('ticker-input'), { target: { value: 'NVDA' } })
    fireEvent.click(screen.getByTestId('run-btn'))

    await waitFor(() => expect(onPremiumRequired).toHaveBeenCalled())
    expect(screen.queryByTestId('run-error')).not.toBeInTheDocument()
  })

  it('validation 400 shows enter valid ticker message', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({ detail: { error: { code: 'VALIDATION_INVALID_PARAMETER' } } }),
        { status: 400 },
      ),
    ))
    render(wrap(<RunForm onNote={vi.fn()} onPending={vi.fn()} onPremiumRequired={vi.fn()} />))

    fireEvent.change(screen.getByTestId('ticker-input'), { target: { value: 'BAD' } })
    fireEvent.click(screen.getByTestId('run-btn'))

    await waitFor(() => expect(screen.getByTestId('run-error')).toBeInTheDocument())
    expect(screen.getByTestId('run-error').textContent).toContain('valid US ticker')
  })
})
