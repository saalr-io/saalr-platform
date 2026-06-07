import type React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import * as oms from '../../lib/oms'
import { usePaperTradeStrategy } from './usePaperTrade'
import type { StrategyConfig } from '../../lib/strategies'

const CONFIG: StrategyConfig = {
  underlying: 'SPY',
  legs: [{ kind: 'option', option_type: 'CALL', side: 'BUY', strike: 580, expiry: '2026-12-18', qty: 1 }],
}
const RESULT = { broker_account_id: 'a1', results: [{ leg_index: 0, kind: 'option', status: 'filled' }], placed: 1, rejected: 0 }

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

describe('usePaperTradeStrategy', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('reuses an existing paper account', async () => {
    vi.spyOn(oms, 'listBrokerAccounts').mockResolvedValue({ broker_accounts: [
      { broker_account_id: 'a1', broker: 'paper', account_label: 'Practice', is_paper: true, status: 'active' } as never] })
    const create = vi.spyOn(oms, 'createBrokerAccount')
    const place = vi.spyOn(oms, 'placeStrategy').mockResolvedValue(RESULT as never)
    const { result } = renderHook(() => usePaperTradeStrategy(), { wrapper: wrapper() })
    result.current.mutate(CONFIG)
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(create).not.toHaveBeenCalled()
    expect(place).toHaveBeenCalledWith({ broker_account_id: 'a1', underlying: 'SPY', legs: CONFIG.legs })
  })

  it('creates a Practice account when none exists', async () => {
    vi.spyOn(oms, 'listBrokerAccounts').mockResolvedValue({ broker_accounts: [] })
    const create = vi.spyOn(oms, 'createBrokerAccount').mockResolvedValue(
      { broker_account_id: 'new', broker: 'paper', account_label: 'Practice', is_paper: true, status: 'active' } as never)
    const place = vi.spyOn(oms, 'placeStrategy').mockResolvedValue({ ...RESULT, broker_account_id: 'new' } as never)
    const { result } = renderHook(() => usePaperTradeStrategy(), { wrapper: wrapper() })
    result.current.mutate(CONFIG)
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(create).toHaveBeenCalledWith('Practice')
    expect(place).toHaveBeenCalledWith({ broker_account_id: 'new', underlying: 'SPY', legs: CONFIG.legs })
  })
})
