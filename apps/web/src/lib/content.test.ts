import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  listModules, getModule, completeModule, getProgress,
  searchContent, askAssistant, EntitlementError,
} from './content'

const MODULE: import('./content').ModuleMeta = {
  slug: 'options-101', title: 'Options 101', summary: 'Intro', order: 1,
  min_tier: 'free', est_minutes: 10, locked: false, status: 'not_started',
}

describe('content client', () => {
  beforeEach(() => vi.unstubAllGlobals())

  // ── listModules ──────────────────────────────────────────────────────────

  it('listModules: returns parsed response on 200', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ modules: [MODULE], completed: 0, in_progress: 0, total: 1 }), { status: 200 }),
    ))
    const r = await listModules()
    expect(r.modules).toHaveLength(1)
    expect(r.modules[0].slug).toBe('options-101')
    expect(r.total).toBe(1)
  })

  it('listModules: throws EntitlementError on 402', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({ detail: { error: { code: 'ENTITLEMENT_CONTENT_REQUIRES_PRO' } } }),
        { status: 402 },
      ),
    ))
    await expect(listModules()).rejects.toBeInstanceOf(EntitlementError)
  })

  // ── getModule ────────────────────────────────────────────────────────────

  it('getModule: returns detail with body on 200', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ ...MODULE, body: '# Hello' }), { status: 200 }),
    ))
    const r = await getModule('options-101')
    expect(r.body).toBe('# Hello')
    expect(r.slug).toBe('options-101')
  })

  it('getModule: uses the slug in the URL', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ ...MODULE, body: '' }), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)
    await getModule('greeks-deep-dive')
    expect(String((fetchMock.mock.calls[0] as unknown[])[0])).toContain('greeks-deep-dive')
  })

  it('getModule: throws EntitlementError on 402', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({ detail: { error: { code: 'ENTITLEMENT_CONTENT_REQUIRES_PRO' } } }),
        { status: 402 },
      ),
    ))
    await expect(getModule('pro-module')).rejects.toBeInstanceOf(EntitlementError)
  })

  it('getModule: throws Error with code on 404', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({ detail: { error: { code: 'RESOURCE_NOT_FOUND' } } }),
        { status: 404 },
      ),
    ))
    await expect(getModule('missing')).rejects.toThrow('RESOURCE_NOT_FOUND')
  })

  // ── completeModule ───────────────────────────────────────────────────────

  it('completeModule: POSTs to the right URL and returns completion', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({ slug: 'options-101', status: 'completed', completed_at: '2026-06-03T00:00:00Z' }),
        { status: 200 },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    const r = await completeModule('options-101')
    expect(r.status).toBe('completed')
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(String(url)).toContain('options-101/complete')
    expect(init.method).toBe('POST')
  })

  // ── getProgress ──────────────────────────────────────────────────────────

  it('getProgress: returns progress data on 200', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({ completed: 2, in_progress: 1, total: 5, modules: [] }),
        { status: 200 },
      ),
    ))
    const r = await getProgress()
    expect(r.completed).toBe(2)
    expect(r.total).toBe(5)
  })

  // ── searchContent ────────────────────────────────────────────────────────

  it('searchContent: includes q param in URL', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ results: [] }), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)
    await searchContent('delta hedging')
    const url = String((fetchMock.mock.calls[0] as unknown[])[0])
    expect(url).toContain('q=delta+hedging')
    expect(url).toContain('/content/search')
  })

  it('searchContent: returns results array on 200', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({ results: [{ slug: 'options-101', title: 'Options 101', snippet: '...', score: 0.9, locked: false }] }),
        { status: 200 },
      ),
    ))
    const r = await searchContent('options')
    expect(r.results[0].slug).toBe('options-101')
  })

  // ── askAssistant ─────────────────────────────────────────────────────────

  it('askAssistant: POSTs question and returns answer on 200', async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          answer: 'Delta is the rate of change.',
          citations: [{ slug: 'greeks', title: 'Greeks' }],
          model: 'gpt-4o',
          usage: { prompt_tokens: 10, completion_tokens: 20 },
        }),
        { status: 200 },
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    const r = await askAssistant('What is delta?')
    expect(r.answer).toBe('Delta is the rate of change.')
    expect(r.citations[0].slug).toBe('greeks')
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toMatchObject({ question: 'What is delta?' })
  })

  it('askAssistant: throws EntitlementError on 402', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({ detail: { error: { code: 'ENTITLEMENT_ASK_REQUIRES_PRO' } } }),
        { status: 402 },
      ),
    ))
    await expect(askAssistant('anything')).rejects.toBeInstanceOf(EntitlementError)
  })

  it('askAssistant: throws Error with LLM_UNAVAILABLE code on 502', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({ detail: { error: { code: 'LLM_UNAVAILABLE' } } }),
        { status: 502 },
      ),
    ))
    await expect(askAssistant('anything')).rejects.toThrow('LLM_UNAVAILABLE')
  })
})
