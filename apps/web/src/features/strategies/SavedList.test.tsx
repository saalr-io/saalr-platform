import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SavedList } from './SavedList'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}

const strat = {
  strategy_id: 's1', name: 'My Spread', description: null, state: 'draft', market: 'US',
  config: { underlying: 'AAPL', legs: [] }, created_at: '2026-05-30T00:00:00Z', updated_at: '2026-05-30T00:00:00Z',
}

describe('SavedList', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('lists strategies and loads one', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ strategies: [strat], next_cursor: null }), { status: 200 })))
    const onLoad = vi.fn()
    render(wrap(<SavedList onLoad={onLoad} />))
    const item = await screen.findByText('My Spread')
    fireEvent.click(item)
    await waitFor(() => expect(onLoad).toHaveBeenCalledWith(expect.objectContaining({ strategy_id: 's1' })))
  })
})
