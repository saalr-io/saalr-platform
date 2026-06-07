import { describe, it, expect, vi, beforeEach } from 'vitest'
import { runResearch, listNotes, getNote, getTranscript, EntitlementError } from './research'

// ── fixtures ───────────────────────────────────────────────────────────────

const SUCCEEDED_NOTE = {
  note_id: 'n1',
  ticker: 'AAPL',
  market: 'US',
  summary: '## Overview\nSolid fundamentals.',
  signals: {
    spot: 192.5,
    vol_forecast: { horizon: 30, primary_forecast: 0.28, status: 'stable' },
    sentiment: { score: 0.72, label: 'Bullish', confident: true, as_of: '2026-06-03' },
  },
  sources: [{ slug: 'sec-10k', title: 'SEC 10-K' }],
  model: 'claude-3-opus',
  usage: { prompt_tokens: 1000, completion_tokens: 500 },
  cost_usd: '0.042', // wire format: a string (Decimal)
  status: 'succeeded',
  cached: false,
  created_at: '2026-06-03T10:00:00Z',
}

const ACCEPTED = {
  note_id: 'n2',
  status: 'queued',
  poll_url: '/research/notes/n2',
}

describe('research client', () => {
  beforeEach(() => vi.unstubAllGlobals())

  // ── runResearch ────────────────────────────────────────────────────────

  it('runResearch: POSTs to /research/run with body', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify(SUCCEEDED_NOTE), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const r = await runResearch({ ticker: 'AAPL' })
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(String(url)).toContain('/research/run')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toMatchObject({ ticker: 'AAPL' })
    expect(r.status).toBe('succeeded')
  })

  it('runResearch: 200 returns succeeded note (discriminated on status)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify(SUCCEEDED_NOTE), { status: 200 }),
    ))
    const r = await runResearch({ ticker: 'AAPL' })
    expect(r.status).toBe('succeeded')
    if (r.status === 'succeeded') {
      expect(r.ticker).toBe('AAPL')
      expect(r.summary).toContain('Solid fundamentals')
    }
  })

  it('runResearch: 202 returns accepted run with poll_url', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify(ACCEPTED), { status: 202 }),
    ))
    const r = await runResearch({ ticker: 'TSLA' })
    expect(r.status).toBe('queued')
    if (r.status === 'queued' || r.status === 'running') {
      expect(r.poll_url).toBe('/research/notes/n2')
    }
  })

  it('runResearch: 402 premium code throws EntitlementError with correct code', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({ detail: { error: { code: 'ENTITLEMENT_RESEARCH_AGENT_REQUIRES_PREMIUM' } } }),
        { status: 402 },
      ),
    ))
    const err = await runResearch({ ticker: 'AAPL' }).catch((e) => e)
    expect(err).toBeInstanceOf(EntitlementError)
    expect((err as EntitlementError).code).toBe('ENTITLEMENT_RESEARCH_AGENT_REQUIRES_PREMIUM')
  })

  it('runResearch: 402 budget code throws EntitlementError with budget code', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({ detail: { error: { code: 'RESEARCH_BUDGET_EXCEEDED' } } }),
        { status: 402 },
      ),
    ))
    const err = await runResearch({ ticker: 'AAPL' }).catch((e) => e)
    expect(err).toBeInstanceOf(EntitlementError)
    expect((err as EntitlementError).code).toBe('RESEARCH_BUDGET_EXCEEDED')
  })

  it('runResearch: 429 throws Error with RATE_LIMIT code', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({ detail: { error: { code: 'RATE_LIMIT_RESEARCH_DAILY_EXCEEDED' } } }),
        { status: 429 },
      ),
    ))
    await expect(runResearch({ ticker: 'AAPL' })).rejects.toThrow('RATE_LIMIT_RESEARCH_DAILY_EXCEEDED')
  })

  it('runResearch: 400 throws Error with VALIDATION code', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({ detail: { error: { code: 'VALIDATION_INVALID_PARAMETER' } } }),
        { status: 400 },
      ),
    ))
    await expect(runResearch({ ticker: '123' })).rejects.toThrow('VALIDATION_INVALID_PARAMETER')
  })

  // ── listNotes ──────────────────────────────────────────────────────────

  it('listNotes: GETs /research/notes with default limit', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ notes: [], next_cursor: null }), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const r = await listNotes()
    const url = String((fetchMock.mock.calls[0] as unknown[])[0])
    expect(url).toContain('/research/notes')
    expect(url).toContain('limit=20')
    expect(r.notes).toHaveLength(0)
    expect(r.next_cursor).toBeNull()
  })

  it('listNotes: passes cursor param when provided', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ notes: [], next_cursor: null }), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)
    await listNotes('abc123')
    const url = String((fetchMock.mock.calls[0] as unknown[])[0])
    expect(url).toContain('cursor=abc123')
  })

  it('listNotes: 402 premium throws EntitlementError', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({ detail: { error: { code: 'ENTITLEMENT_RESEARCH_AGENT_REQUIRES_PREMIUM' } } }),
        { status: 402 },
      ),
    ))
    await expect(listNotes()).rejects.toBeInstanceOf(EntitlementError)
  })

  // ── getNote ────────────────────────────────────────────────────────────

  it('getNote: GETs /research/notes/{id}', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ note_id: 'n1', status: 'running' }), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const r = await getNote('n1')
    const url = String((fetchMock.mock.calls[0] as unknown[])[0])
    expect(url).toContain('/research/notes/n1')
    expect(r.status).toBe('running')
  })

  it('getNote: returns succeeded note shape', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify(SUCCEEDED_NOTE), { status: 200 }),
    ))
    const r = await getNote('n1')
    expect(r.status).toBe('succeeded')
  })

  // ── getTranscript ──────────────────────────────────────────────────────

  it('getTranscript: GETs /research/notes/{id}/transcript', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({ note_id: 'n1', steps: [{ role: 'fundamentals', memo: 'Strong revenue growth.' }] }),
        { status: 200 },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    const r = await getTranscript('n1')
    const url = String((fetchMock.mock.calls[0] as unknown[])[0])
    expect(url).toContain('/research/notes/n1/transcript')
    expect(r.steps[0].role).toBe('fundamentals')
  })

  it('getTranscript: 404 throws Error with RESOURCE_NOT_FOUND', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({ detail: { error: { code: 'RESOURCE_NOT_FOUND' } } }),
        { status: 404 },
      ),
    ))
    await expect(getTranscript('n1')).rejects.toThrow('RESOURCE_NOT_FOUND')
  })
})
