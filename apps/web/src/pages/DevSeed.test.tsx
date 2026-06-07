import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { DevSeed } from './DevSeed'
import * as dev from '../lib/dev'

describe('DevSeed', () => {
  beforeEach(() => { vi.restoreAllMocks() })
  afterEach(() => { vi.useRealTimers() })

  it('backfills bars and logs the result', async () => {
    const spy = vi.spyOn(dev, 'seedBars').mockResolvedValue(
      { symbol: 'AAPL', rows_upserted: 250, first: '2025-01-01', last: '2026-01-01' })
    render(<DevSeed />)
    fireEvent.click(screen.getByTestId('seed-bars-btn'))
    await waitFor(() => expect(spy).toHaveBeenCalledWith('AAPL', 400))
    await waitFor(() => expect(screen.getByTestId('seed-log').textContent).toContain('250'))
  })

  it('captures a snapshot and logs total_snapshots', async () => {
    const spy = vi.spyOn(dev, 'seedChain').mockResolvedValue(
      { ticker: 'AAPL', as_of: '2026-06-07T10:00:00+00:00', contracts: 12, total_snapshots: 3 })
    render(<DevSeed />)
    fireEvent.click(screen.getByTestId('seed-chain-btn'))
    await waitFor(() => expect(spy).toHaveBeenCalledWith('AAPL'))
    await waitFor(() => expect(screen.getByTestId('seed-log').textContent).toContain('total_snapshots=3'))
  })

  it('repeat loop fires N times on the interval then auto-stops', async () => {
    vi.useFakeTimers()
    const spy = vi.spyOn(dev, 'seedChain').mockResolvedValue(
      { ticker: 'AAPL', as_of: 'x', contracts: 1, total_snapshots: 1 })
    render(<DevSeed />)
    fireEvent.change(screen.getByTestId('repeat-every-min'), { target: { value: '1' } })
    fireEvent.change(screen.getByTestId('repeat-times'), { target: { value: '3' } })
    fireEvent.click(screen.getByTestId('repeat-start'))
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000 * 3) })
    expect(spy).toHaveBeenCalledTimes(3)
  })
})
