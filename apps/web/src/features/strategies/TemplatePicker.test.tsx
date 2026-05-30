import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TemplatePicker } from './TemplatePicker'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}

describe('TemplatePicker', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('lists templates and applies one', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (String(url).endsWith('/templates')) {
        return new Response(JSON.stringify({ templates: [
          { key: 'bull_call_spread', name: 'Bull Call Spread', category: 'bullish', description: 'x' }] }), { status: 200 })
      }
      if (String(url).includes('/templates/bull_call_spread/build')) {
        return new Response(JSON.stringify({ underlying: 'AAPL', legs: [
          { kind: 'option', option_type: 'CALL', side: 'BUY', strike: 100, expiry: '2026-12-18', qty: 1 },
          { kind: 'option', option_type: 'CALL', side: 'SELL', strike: 110, expiry: '2026-12-18', qty: 1 }] }), { status: 200 })
      }
      return new Response('{}', { status: 200 })
    }))
    const onApply = vi.fn()
    render(wrap(<TemplatePicker underlying="AAPL" expiry="2026-12-18" atmStrike={100} onApply={onApply} />))
    const chip = await screen.findByText('Bull Call Spread')
    fireEvent.click(chip)
    await waitFor(() => expect(onApply).toHaveBeenCalled())
    expect(onApply.mock.calls.at(-1)![0].legs).toHaveLength(2)
  })
})
