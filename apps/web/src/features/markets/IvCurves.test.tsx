import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { IvCurves } from './IvCurves'
import type { IvSurface, Greeks } from '../../lib/market'

const G = (iv: number): Greeks => ({ price: 1, delta: 0.5, gamma: 0.01, theta: -0.02, vega: 0.1, rho: 0.05, iv })

const SURFACE: IvSurface = {
  ticker: 'SPY', market: 'US', as_of: 'x', spot: 100, data_provider: 'massive', model: 'bsm',
  risk_free_source: 'fred', freshness_ms: 0,
  expiries: [
    { expiry: '2026-07-17', strikes: [
      { strike: 95, calls: G(0.22), puts: G(0.24) },
      { strike: 100, calls: G(0.20), puts: G(0.21) },
      { strike: 105, calls: G(0.23), puts: G(0.25) }] },
    { expiry: '2026-08-21', strikes: [
      { strike: 100, calls: G(0.26), puts: G(0.27) }] },
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

  it('shows an empty state (no crash) for a surface with no expiries', () => {
    render(<IvCurves surface={{ ...SURFACE, expiries: [] }} expiry="" />)
    expect(screen.getByTestId('iv-empty')).toBeInTheDocument()
    expect(screen.queryByTestId('iv-smile')).toBeNull()
  })
})
