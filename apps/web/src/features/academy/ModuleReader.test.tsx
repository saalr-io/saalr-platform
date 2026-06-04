import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ModuleReader } from './ModuleReader'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <MemoryRouter><QueryClientProvider client={qc}>{ui}</QueryClientProvider></MemoryRouter>
}

const MODULE_DETAIL = {
  slug: 'options-101', title: 'Options 101', summary: 'An intro to options.',
  order: 1, min_tier: 'free' as const, est_minutes: 10, locked: false,
  status: 'not_started' as const, body: '# Hello\n\nThis is the lesson body.',
}

describe('ModuleReader', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('renders title and summary on success', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify(MODULE_DETAIL), { status: 200 }),
    ))
    render(wrap(<ModuleReader slug="options-101" />))
    expect(await screen.findByText('Options 101')).toBeTruthy()
    expect(screen.getByText('An intro to options.')).toBeTruthy()
  })

  it('renders markdown body', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify(MODULE_DETAIL), { status: 200 }),
    ))
    render(wrap(<ModuleReader slug="options-101" />))
    expect(await screen.findByText('Hello')).toBeTruthy()
    expect(screen.getByText('This is the lesson body.')).toBeTruthy()
  })

  it('shows Mark complete button when not completed', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify(MODULE_DETAIL), { status: 200 }),
    ))
    render(wrap(<ModuleReader slug="options-101" />))
    expect(await screen.findByTestId('complete-btn')).toBeTruthy()
    expect(screen.getByTestId('complete-btn').textContent).toBe('Mark complete')
  })

  it('shows Completed button when status is completed', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({ ...MODULE_DETAIL, status: 'completed' }),
        { status: 200 },
      ),
    ))
    render(wrap(<ModuleReader slug="options-101" />))
    const btn = await screen.findByTestId('complete-btn')
    expect(btn.textContent).toBe('✓ Completed')
    expect(btn).toBeDisabled()
  })

  it('calls complete endpoint on Mark complete click', async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).includes('/complete')) {
        return new Response(
          JSON.stringify({ slug: 'options-101', status: 'completed', completed_at: '2026-06-03T00:00:00Z' }),
          { status: 200 },
        )
      }
      return new Response(JSON.stringify(MODULE_DETAIL), { status: 200 })
    })
    vi.stubGlobal('fetch', fetchMock)
    render(wrap(<ModuleReader slug="options-101" />))
    const btn = await screen.findByTestId('complete-btn')
    fireEvent.click(btn)
    await waitFor(() => {
      const calls = fetchMock.mock.calls.map(([u]) => String(u))
      expect(calls.some((u) => u.includes('/complete'))).toBe(true)
    })
  })

  it('renders upgrade nudge when fetch returns 402', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({ detail: { error: { code: 'ENTITLEMENT_CONTENT_REQUIRES_PRO' } } }),
        { status: 402 },
      ),
    ))
    render(wrap(<ModuleReader slug="pro-module" />))
    expect(await screen.findByTestId('upgrade-nudge')).toBeTruthy()
    expect(screen.getByText('This lesson needs Pro')).toBeTruthy()
  })

  it('renders error message on 404', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({ detail: { error: { code: 'RESOURCE_NOT_FOUND' } } }),
        { status: 404 },
      ),
    ))
    render(wrap(<ModuleReader slug="missing" />))
    expect(await screen.findByTestId('reader-error')).toBeTruthy()
  })
})


