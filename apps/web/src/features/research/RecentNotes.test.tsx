import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RecentNotes } from './RecentNotes'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}

// cost_usd arrives as a string (Decimal) on the wire — exercise the real format.
const ROWS = [
  { note_id: 'n1', ticker: 'AAPL', market: 'US' as const, model: 'claude-3-opus', cost_usd: '0.042', created_at: '2026-06-03T10:00:00Z' },
  { note_id: 'n2', ticker: 'TSLA', market: 'US' as const, model: 'claude-3-opus', cost_usd: null, created_at: '2026-06-02T09:00:00Z' },
]

describe('RecentNotes', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('lists note rows', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ notes: ROWS, next_cursor: null }), { status: 200 }),
    ))
    render(wrap(<RecentNotes activeNoteId={null} onSelect={vi.fn()} />))

    await waitFor(() => expect(screen.getByTestId('recent-notes')).toBeInTheDocument())
    expect(screen.getByTestId('note-row-n1').textContent).toContain('AAPL')
    expect(screen.getByTestId('note-row-n2').textContent).toContain('TSLA')
    // string cost formats to $0.042; null cost renders the em-dash (no crash)
    expect(screen.getByTestId('note-row-n1').textContent).toContain('$0.042')
    expect(screen.getByTestId('note-row-n2').textContent).toContain('—')
  })

  it('calls onSelect with the note_id when a row is clicked', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ notes: ROWS, next_cursor: null }), { status: 200 }),
    ))
    const onSelect = vi.fn()
    render(wrap(<RecentNotes activeNoteId={null} onSelect={onSelect} />))

    await waitFor(() => expect(screen.getByTestId('note-row-n1')).toBeInTheDocument())
    fireEvent.click(screen.getByTestId('note-row-n1'))
    expect(onSelect).toHaveBeenCalledWith('n1')
  })

  it('shows empty state when no notes exist', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ notes: [], next_cursor: null }), { status: 200 }),
    ))
    render(wrap(<RecentNotes activeNoteId={null} onSelect={vi.fn()} />))

    await waitFor(() => expect(screen.getByTestId('recent-notes-empty')).toBeInTheDocument())
  })

  it('shows nothing when there is an error (page handles gate)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({ detail: { error: { code: 'ENTITLEMENT_RESEARCH_AGENT_REQUIRES_PREMIUM' } } }),
        { status: 402 },
      ),
    ))
    render(wrap(<RecentNotes activeNoteId={null} onSelect={vi.fn()} />))

    // No notes list and no error panel rendered (page-level gate)
    await waitFor(() => expect(screen.queryByTestId('recent-notes')).not.toBeInTheDocument())
    expect(screen.queryByTestId('recent-notes-empty')).not.toBeInTheDocument()
  })
})
