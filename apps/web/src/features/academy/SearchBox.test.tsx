import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SearchBox } from './SearchBox'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}

describe('SearchBox', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('renders a search input', () => {
    render(wrap(<SearchBox onSelect={vi.fn()} />))
    expect(screen.getByTestId('search-input')).toBeTruthy()
  })

  it('does NOT call fetch when input is empty', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ results: [] }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    render(wrap(<SearchBox onSelect={vi.fn()} />))
    // wait a tick — no fetch should happen
    await new Promise((r) => setTimeout(r, 50))
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('shows results after debounce', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({
          results: [{ slug: 'options-101', title: 'Options 101', snippet: 'Intro to options', score: 0.9, locked: false }],
        }),
        { status: 200 },
      ),
    ))
    render(wrap(<SearchBox onSelect={vi.fn()} />))
    fireEvent.change(screen.getByTestId('search-input'), { target: { value: 'options' } })
    expect(await screen.findByTestId('search-results')).toBeTruthy()
    expect(screen.getByText('Options 101')).toBeTruthy()
    expect(screen.getByText('Intro to options')).toBeTruthy()
  })

  it('shows lock badge for locked search result', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({
          results: [{ slug: 'greeks', title: 'Greeks', snippet: 'Deep dive', score: 0.8, locked: true }],
        }),
        { status: 200 },
      ),
    ))
    render(wrap(<SearchBox onSelect={vi.fn()} />))
    fireEvent.change(screen.getByTestId('search-input'), { target: { value: 'greeks' } })
    await screen.findByTestId('search-results')
    expect(screen.getByText('PRO')).toBeTruthy()
  })

  it('calls onSelect and clears input when a result is clicked', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({
          results: [{ slug: 'options-101', title: 'Options 101', snippet: '...', score: 0.9, locked: false }],
        }),
        { status: 200 },
      ),
    ))
    const onSelect = vi.fn()
    render(wrap(<SearchBox onSelect={onSelect} />))
    fireEvent.change(screen.getByTestId('search-input'), { target: { value: 'options' } })
    await screen.findByTestId('search-hit-options-101')
    fireEvent.click(screen.getByTestId('search-hit-options-101'))
    expect(onSelect).toHaveBeenCalledWith('options-101')
    // input cleared
    expect((screen.getByTestId('search-input') as HTMLInputElement).value).toBe('')
  })

  it('shows no-results message when results empty', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ results: [] }), { status: 200 }),
    ))
    render(wrap(<SearchBox onSelect={vi.fn()} />))
    fireEvent.change(screen.getByTestId('search-input'), { target: { value: 'xyznotfound' } })
    await waitFor(() => expect(screen.queryByTestId('no-results')).toBeTruthy())
  })
})


