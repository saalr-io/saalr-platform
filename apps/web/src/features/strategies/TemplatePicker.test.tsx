import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TemplatePicker } from './TemplatePicker'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}

const TEMPLATES = [
  { key: 'bull_call_spread', name: 'Bull Call Spread', description: 'x', market_view: 'bullish', vol_view: 'neutral', net: 'debit', risk: 'defined', reward: 'defined', legs: 2, complexity: 'beginner' },
  { key: 'short_strangle', name: 'Short Strangle', description: 'y', market_view: 'neutral', vol_view: 'short_vol', net: 'credit', risk: 'undefined', reward: 'defined', legs: 2, complexity: 'advanced' },
]

function stubFetch() {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (String(url).endsWith('/templates')) {
      return new Response(JSON.stringify({ templates: TEMPLATES }), { status: 200 })
    }
    if (String(url).includes('/templates/bull_call_spread/build')) {
      return new Response(JSON.stringify({ underlying: 'AAPL', legs: [
        { kind: 'option', option_type: 'CALL', side: 'BUY', strike: 100, expiry: '2026-12-18', qty: 1 },
        { kind: 'option', option_type: 'CALL', side: 'SELL', strike: 110, expiry: '2026-12-18', qty: 1 }] }), { status: 200 })
    }
    return new Response('{}', { status: 200 })
  }))
}

describe('TemplatePicker', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('lists templates and applies one', async () => {
    stubFetch()
    const onApply = vi.fn()
    render(wrap(<TemplatePicker underlying="AAPL" expiry="2026-12-18" atmStrike={100} onApply={onApply} />))
    const card = await screen.findByTestId('tpl-bull_call_spread')
    fireEvent.click(card)
    await waitFor(() => expect(onApply).toHaveBeenCalled())
    expect(onApply.mock.calls.at(-1)![0].legs).toHaveLength(2)
  })

  it('flags undefined risk and filters by market view', async () => {
    stubFetch()
    render(wrap(<TemplatePicker underlying="AAPL" expiry="2026-12-18" atmStrike={100} onApply={vi.fn()} />))
    await screen.findByTestId('tpl-bull_call_spread')
    expect(screen.getByText(/undefined risk/i)).toBeInTheDocument()
    fireEvent.click(screen.getByText('Bearish'))
    await waitFor(() => expect(screen.getByTestId('tpl-empty')).toBeInTheDocument())
  })
})
