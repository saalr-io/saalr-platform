import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { IvCurves } from './IvCurves'
import type { IvSurface } from '../../lib/market'

const SURFACE: IvSurface = {
  ticker: 'SPY', market: 'US', as_of: 'x', spot: 100, data_provider: 'massive', model: 'bsm',
  risk_free_source: 'fred', freshness_ms: 0,
  expiries: [
    { expiry: '2026-07-17', strikes: [
      { strike: 95, iv_call: 0.22, iv_put: 0.24 },
      { strike: 100, iv_call: 0.20, iv_put: 0.21 },
      { strike: 105, iv_call: 0.23, iv_put: 0.25 }] },
    { expiry: '2026-08-21', strikes: [
      { strike: 100, iv_call: 0.26, iv_put: 0.27 }] },
  ],
}

describe('IvCurves', () => {
  it('renders the smile and term-structure charts', () => {
    render(<IvCurves surface={SURFACE} expiry="2026-07-17" />)
    expect(screen.getByTestId('iv-smile')).toBeInTheDocument()
    expect(screen.getByTestId('iv-term-structure')).toBeInTheDocument()
    expect(screen.getByTestId('iv-smile-calls').getAttribute('points')!.trim().split(' ').length).toBe(3)
    expect(screen.getByTestId('iv-term-line').getAttribute('points')!.trim().split(' ').length).toBe(2)
  })

  it('skips strikes missing a side without crashing', () => {
    const s: IvSurface = {
      ...SURFACE,
      expiries: [{ expiry: '2026-07-17', strikes: [
        { strike: 95, iv_call: 0.22, iv_put: null },   // one-sided -> excluded
        { strike: 100, iv_call: 0.20, iv_put: 0.21 }] }],
    }
    render(<IvCurves surface={s} expiry="2026-07-17" />)
    // only the two-sided strike contributes a smile point
    expect(screen.getByTestId('iv-smile-calls').getAttribute('points')!.trim().split(' ').length).toBe(1)
  })

  it('shows an empty state (no crash) for a surface with no expiries', () => {
    render(<IvCurves surface={{ ...SURFACE, expiries: [] }} expiry="" />)
    expect(screen.getByTestId('iv-empty')).toBeInTheDocument()
    expect(screen.queryByTestId('iv-smile')).toBeNull()
  })

  it('shows an empty state when no strike has both sides', () => {
    const s: IvSurface = {
      ...SURFACE,
      expiries: [{ expiry: '2026-07-17', strikes: [{ strike: 100, iv_call: 0.2, iv_put: null }] }],
    }
    render(<IvCurves surface={s} expiry="2026-07-17" />)
    expect(screen.getByTestId('iv-empty')).toBeInTheDocument()
  })

  it('shows contextual info hints on the charts', () => {
    render(<IvCurves surface={SURFACE} expiry="2026-07-17" />)
    expect(screen.getAllByTestId('info-hint').length).toBeGreaterThanOrEqual(3)
  })

  it('labels both axes on the smile and term-structure charts', () => {
    render(<IvCurves surface={SURFACE} expiry="2026-07-17" />)
    const smile = screen.getByTestId('iv-smile')
    expect(smile.textContent).toContain('strike')   // x-axis title
    expect(smile.textContent).toContain('IV %')     // y-axis title
    expect(smile.textContent).toContain('95')       // min-strike tick
    const term = screen.getByTestId('iv-term-structure')
    expect(term.textContent).toContain('expiry')    // x-axis title
    expect(term.textContent).toContain('07-17')     // first expiry tick (MM-DD)
  })
})
