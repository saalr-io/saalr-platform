import type React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { TemplatePicker } from './TemplatePicker'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>
}

describe('TemplatePicker per-strategy help', () => {
  it('renders an info-hint on a card and clicking it does NOT apply the template', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (String(url).endsWith('/templates')) return new Response(JSON.stringify({ templates: [
        { key: 'bull_call_spread', name: 'Bull Call Spread', description: 'x', market_view: 'bullish', vol_view: 'neutral', net: 'debit', risk: 'defined', reward: 'defined', legs: 2, complexity: 'beginner' }] }), { status: 200 })
      return new Response('{}', { status: 200 })
    }))
    const onApply = vi.fn(); const onPick = vi.fn()
    render(wrap(<TemplatePicker underlying="AAPL" expiry="2026-12-18" atmStrike={100} onApply={onApply} onPick={onPick} />))
    const hint = await screen.findByTestId('info-hint')
    fireEvent.click(hint)
    expect(onPick).not.toHaveBeenCalled()
    expect(screen.getByTestId('info-hint-popover')).toBeInTheDocument()
  })
})
