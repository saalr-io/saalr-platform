import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { NoteView } from './NoteView'
import type { ResearchNote } from '../../lib/research'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}

const FULL_NOTE: ResearchNote = {
  note_id: 'n1',
  ticker: 'AAPL',
  market: 'US',
  summary: '## Overview\n**Apple** shows solid fundamentals.',
  signals: {
    spot: 192.5,
    vol_forecast: { horizon: 30, primary_forecast: 0.28, status: 'stable' },
    sentiment: { score: 0.72, label: 'Bullish', confident: true, as_of: '2026-06-03' },
  },
  sources: [{ slug: 'sec-10k', title: 'SEC 10-K' }],
  model: 'claude-3-opus',
  usage: { prompt_tokens: 1000, completion_tokens: 500 },
  cost_usd: '0.042', // wire format: a string (Decimal), not a number
  status: 'succeeded',
  created_at: '2026-06-03T10:00:00Z',
}

const NULL_SIGNALS_NOTE: ResearchNote = {
  ...FULL_NOTE,
  note_id: 'n2',
  signals: { spot: 192.5, vol_forecast: null, sentiment: null },
}

describe('NoteView', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('renders the summary markdown', () => {
    render(wrap(<NoteView note={FULL_NOTE} />))
    expect(screen.getByTestId('note-summary')).toBeInTheDocument()
    // The Markdown component renders "Overview" as a heading
    expect(screen.getByTestId('note-summary').textContent).toContain('Overview')
  })

  it('renders signal cards with spot, vol forecast, and sentiment', () => {
    render(wrap(<NoteView note={FULL_NOTE} />))
    const cards = screen.getByTestId('signal-cards')
    expect(cards.textContent).toContain('192.50')
    expect(cards.textContent).toContain('28.0%')
    expect(cards.textContent).toContain('Bullish')
  })

  it('renders "—" for null vol forecast', () => {
    render(wrap(<NoteView note={NULL_SIGNALS_NOTE} />))
    const cards = screen.getByTestId('signal-cards')
    // Vol forecast card should show em-dash
    expect(cards.textContent).toContain('—')
  })

  it('renders "—" for null sentiment', () => {
    render(wrap(<NoteView note={NULL_SIGNALS_NOTE} />))
    const cards = screen.getByTestId('signal-cards')
    expect(cards.textContent).toContain('—')
  })

  it('renders sources', () => {
    render(wrap(<NoteView note={FULL_NOTE} />))
    expect(screen.getByTestId('note-sources').textContent).toContain('SEC 10-K')
  })

  it('renders footer with model, tokens, and cost', () => {
    render(wrap(<NoteView note={FULL_NOTE} />))
    const footer = screen.getByTestId('note-footer')
    expect(footer.textContent).toContain('claude-3-opus')
    expect(footer.textContent).toContain('1500')   // 1000 + 500
    expect(footer.textContent).toContain('0.0420')
  })

  it('transcript toggle loads steps on click', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({
          note_id: 'n1',
          steps: [
            { role: 'fundamentals', memo: 'Strong revenue growth.', model: 'claude-3-haiku', prompt_tokens: 200, completion_tokens: 80, cost_usd: '0.001' },
            { role: 'sentiment', memo: 'Positive news cycle.' },
          ],
        }),
        { status: 200 },
      ),
    ))
    render(wrap(<NoteView note={FULL_NOTE} />))

    fireEvent.click(screen.getByTestId('transcript-toggle'))

    await waitFor(() => expect(screen.getByTestId('transcript-steps')).toBeInTheDocument())
    expect(screen.getByTestId('step-0').textContent).toContain('Strong revenue growth')
    expect(screen.getByTestId('step-1').textContent).toContain('Positive news cycle')
  })

  it('transcript toggle hides panel when clicked again', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ note_id: 'n1', steps: [] }), { status: 200 }),
    ))
    render(wrap(<NoteView note={FULL_NOTE} />))

    const btn = screen.getByTestId('transcript-toggle')
    fireEvent.click(btn)
    await waitFor(() => expect(screen.getByTestId('transcript-panel')).toBeInTheDocument())

    fireEvent.click(btn)
    expect(screen.queryByTestId('transcript-panel')).not.toBeInTheDocument()
  })
})
