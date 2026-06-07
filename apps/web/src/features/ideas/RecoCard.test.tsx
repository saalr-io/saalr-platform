import type React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { RecoCard } from './RecoCard'
import type { Recommendation } from '../../lib/regime'

const RECO: Recommendation = {
  template_key: 'bull_put_spread', name: 'Bull Put Spread', score: 7, market_view: 'bullish',
  vol_view: 'short_vol', net: 'credit', risk: 'defined', complexity: 'beginner', rationale: 'Fits a bullish view.',
}

function wrap(ui: React.ReactNode) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

describe('RecoCard', () => {
  it('Apply fires onApply', () => {
    const onApply = vi.fn()
    wrap(<RecoCard reco={RECO} onApply={onApply} applying={false} onPaperTrade={vi.fn()} paperState="idle" />)
    fireEvent.click(screen.getByTestId('reco-apply-bull_put_spread'))
    expect(onApply).toHaveBeenCalledWith('bull_put_spread')
  })

  it('Paper-trade opens a confirm and Place fires onPaperTrade', () => {
    const onPaperTrade = vi.fn()
    wrap(<RecoCard reco={RECO} onApply={vi.fn()} applying={false} onPaperTrade={onPaperTrade} paperState="idle" />)
    fireEvent.click(screen.getByTestId('reco-paper-bull_put_spread'))
    expect(screen.getByTestId('reco-confirm-bull_put_spread')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('reco-confirm-place-bull_put_spread'))
    expect(onPaperTrade).toHaveBeenCalledWith('bull_put_spread')
  })

  it('shows a placed result with a Portfolio link', () => {
    wrap(<RecoCard reco={RECO} onApply={vi.fn()} applying={false} onPaperTrade={vi.fn()}
      paperState={{ placed: 2, rejected: 0 }} />)
    const done = screen.getByTestId('reco-paper-done-bull_put_spread')
    expect(done.textContent).toContain('2')
    expect(screen.getByText(/portfolio/i).getAttribute('href')).toBe('/portfolio')
  })
})
