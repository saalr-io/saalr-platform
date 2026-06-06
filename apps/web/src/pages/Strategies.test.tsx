import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { Strategies } from './Strategies'
import * as oms from '../lib/oms'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>
}

const pureResult = {
  expiration_curve: [{ spot: 80, pnl: -400 }, { spot: 130, pnl: 600 }], breakevens: [104],
  max_profit: 600, max_loss: -400, unbounded_profit: false, unbounded_loss: false,
  net_premium: 400, risk_reward: 1.5,
}

describe('Strategies page', () => {
  beforeEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

  it('analyzes and renders the chart + stats', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (String(url).endsWith('/templates')) return new Response(JSON.stringify({ templates: [] }), { status: 200 })
      if (String(url).endsWith('/v1/strategies')) return new Response(JSON.stringify({ strategies: [], next_cursor: null }), { status: 200 })
      return new Response(JSON.stringify(pureResult), { status: 200 })
    }))
    render(wrap(<Strategies />))
    fireEvent.click(screen.getByTestId('analyze-btn'))
    await waitFor(() => expect(screen.getByTestId('payoff-chart')).toBeInTheDocument())
    expect(screen.getByTestId('stat-max-profit')).toHaveTextContent('600')
  })

  it('shows an upgrade nudge on 402 for a live analyze', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (String(url).endsWith('/templates')) return new Response(JSON.stringify({ templates: [] }), { status: 200 })
      if (String(url).endsWith('/v1/strategies')) return new Response(JSON.stringify({ strategies: [], next_cursor: null }), { status: 200 })
      return new Response(JSON.stringify({ detail: { error: { code: 'ENTITLEMENT_VOL_SURFACE_REQUIRES_PRO' } } }), { status: 402 })
    }))
    render(wrap(<Strategies />))
    fireEvent.click(screen.getByTestId('live-toggle'))
    fireEvent.click(screen.getByTestId('analyze-btn'))
    await waitFor(() => expect(screen.getByTestId('upgrade-banner')).toBeInTheDocument())
  })

  it('surfaces a non-entitlement analyze failure', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (String(url).endsWith('/templates')) return new Response(JSON.stringify({ templates: [] }), { status: 200 })
      if (String(url).endsWith('/v1/strategies')) return new Response(JSON.stringify({ strategies: [], next_cursor: null }), { status: 200 })
      return new Response(JSON.stringify({ detail: { error: { code: 'INTERNAL' } } }), { status: 500 })
    }))
    render(wrap(<Strategies />))
    fireEvent.click(screen.getByTestId('analyze-btn'))
    await waitFor(() => expect(screen.getByTestId('error-banner')).toBeInTheDocument())
  })

  it('paper-trades the current config', async () => {
    // the builder's initial loads (templates + strategies) go through fetch
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (String(url).endsWith('/templates')) return new Response(JSON.stringify({ templates: [] }), { status: 200 })
      if (String(url).endsWith('/v1/strategies')) return new Response(JSON.stringify({ strategies: [], next_cursor: null }), { status: 200 })
      return new Response('{}', { status: 200 })
    }))
    // the paper-trade flow goes through the oms module (spied, bypassing fetch)
    const list = vi.spyOn(oms, 'listBrokerAccounts').mockResolvedValue({ broker_accounts: [
      { broker_account_id: 'a1', broker: 'paper', account_label: 'Practice', is_paper: true, status: 'active' } as never] })
    const place = vi.spyOn(oms, 'placeStrategy').mockResolvedValue(
      { broker_account_id: 'a1', results: [], placed: 2, rejected: 0 } as never)
    render(wrap(<Strategies />))
    fireEvent.click(screen.getByTestId('paper-trade-btn'))
    await waitFor(() => expect(place).toHaveBeenCalled())
    expect(list).toHaveBeenCalled()
    await waitFor(() => expect(screen.getByTestId('paper-trade-result')).toBeInTheDocument())
  })
})
