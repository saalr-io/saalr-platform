import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { Start } from './Start'
import * as ob from '../lib/onboarding'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>
}

const REGIME = {
  ticker: 'AAPL', market: 'US', as_of: 'x', approximate: true,
  regime: {
    direction: { label: 'bullish', score: 0.4, detail: 'rising' },
    volatility: { label: 'normal', percentile: 0.5, realized_vol: 18, detail: 'mid' },
    momentum: { label: 'trending', efficiency_ratio: 0.4, detail: 'trend' },
    headline: 'Bullish · Normal vol · Trending', last_close: 195, n_closes: 800,
    premium_available: false, premium: null,
  },
  recommendations: [
    { template_key: 'bull_put_spread', name: 'Bull Put Spread', score: 7, market_view: 'bullish',
      vol_view: 'short_vol', net: 'credit', risk: 'defined', complexity: 'beginner', rationale: 'Fits a bullish view.' },
  ],
}

function stubFetch() {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (String(url).includes('/v1/market/regime')) return new Response(JSON.stringify(REGIME), { status: 200 })
    if (String(url).includes('/onboarding')) return new Response(JSON.stringify({ steps: ['see_regime'], all_done: false }), { status: 200 })
    return new Response('{}', { status: 200 })
  }))
}

describe('Start guided flow', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('renders step 0 with ticker input', () => {
    stubFetch()
    render(wrap(<Start />))
    expect(screen.getByTestId('start-step-ticker')).toBeInTheDocument()
    expect(screen.getByTestId('start-ticker-input')).toBeInTheDocument()
    expect(screen.getByTestId('start-see-regime')).toBeInTheDocument()
  })

  it('advances ticker -> regime and marks see_regime', async () => {
    const spy = vi.spyOn(ob, 'completeStep').mockResolvedValue({ steps: ['see_regime'], all_done: false })
    stubFetch()
    render(wrap(<Start />))
    fireEvent.change(screen.getByTestId('start-ticker-input'), { target: { value: 'AAPL' } })
    fireEvent.click(screen.getByTestId('start-see-regime'))
    expect(await screen.findByTestId('start-step-regime')).toBeInTheDocument()
    await waitFor(() => expect(spy).toHaveBeenCalledWith('see_regime'))
  })

  it('shows paper-trade button in step 1', async () => {
    vi.spyOn(ob, 'completeStep').mockResolvedValue({ steps: ['see_regime'], all_done: false })
    stubFetch()
    render(wrap(<Start />))
    fireEvent.change(screen.getByTestId('start-ticker-input'), { target: { value: 'AAPL' } })
    fireEvent.click(screen.getByTestId('start-see-regime'))
    await screen.findByTestId('start-step-regime')
    expect(screen.getByTestId('start-paper-trade')).toBeInTheDocument()
  })
})
