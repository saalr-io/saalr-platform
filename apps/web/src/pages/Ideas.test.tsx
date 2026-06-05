import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { Ideas } from './Ideas'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>
}

const REGIME = {
  ticker: 'SPY', market: 'US', as_of: 'x', approximate: true,
  regime: {
    direction: { label: 'bullish', score: 0.4, detail: 'rising' },
    volatility: { label: 'normal', percentile: 0.5, realized_vol: 18, detail: 'mid' },
    momentum: { label: 'trending', efficiency_ratio: 0.4, detail: 'trend' },
    headline: 'Bullish · Normal vol · Trending', last_close: 585, n_closes: 800,
    premium_available: false, premium: null,
  },
  recommendations: [
    { template_key: 'bull_put_spread', name: 'Bull Put Spread', score: 7, market_view: 'bullish',
      vol_view: 'short_vol', net: 'credit', risk: 'defined', complexity: 'beginner', rationale: 'Fits a bullish view.' },
  ],
}

function stub() {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (String(url).includes('/v1/market/regime')) return new Response(JSON.stringify(REGIME), { status: 200 })
    if (String(url).includes('/templates/bull_put_spread/build'))
      return new Response(JSON.stringify({ underlying: 'SPY', legs: [] }), { status: 200 })
    return new Response('{}', { status: 200 })
  }))
}

describe('Ideas', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('shows the regime, recommendations, and an upgrade nudge for free users', async () => {
    stub()
    render(wrap(<Ideas />))
    fireEvent.change(screen.getByTestId('idea-ticker'), { target: { value: 'SPY' } })
    fireEvent.click(screen.getByTestId('idea-go'))
    await waitFor(() => expect(screen.getByTestId('regime-panel')).toBeInTheDocument())
    expect(screen.getByTestId('regime-headline').textContent).toContain('Bullish')
    expect(screen.getByTestId('reco-bull_put_spread')).toBeInTheDocument()
    expect(screen.getByTestId('regime-upgrade')).toBeInTheDocument()
  })

  it('Apply builds the chosen template', async () => {
    stub()
    render(wrap(<Ideas />))
    fireEvent.change(screen.getByTestId('idea-ticker'), { target: { value: 'SPY' } })
    fireEvent.click(screen.getByTestId('idea-go'))
    await screen.findByTestId('reco-apply-bull_put_spread')
    fireEvent.click(screen.getByTestId('reco-apply-bull_put_spread'))
    await waitFor(() => {
      const calls = (globalThis.fetch as unknown as { mock: { calls: unknown[][] } }).mock.calls
      expect(calls.some((c) => String(c[0]).includes('/templates/bull_put_spread/build'))).toBe(true)
    })
  })
})
