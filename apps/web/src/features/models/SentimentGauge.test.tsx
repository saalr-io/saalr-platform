import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SentimentGauge } from './SentimentGauge'
import type { Sentiment } from '../../lib/models'

const S = (over: Partial<Sentiment> = {}): Sentiment => ({
  ticker: 'AAPL', market: 'US', score: 0, label: 'neutral', confident: true,
  n_headlines: 12, has_data: true, computed_at: '2026-06-04T10:00:00Z', as_of: '2026-06-04T00:00:00Z', ...over,
})

describe('SentimentGauge', () => {
  it('places the marker past midpoint and labels bullish for a positive score', () => {
    render(<SentimentGauge sentiment={S({ score: 0.6, label: 'bullish' })} />)
    expect(Number(screen.getByTestId('sentiment-marker').getAttribute('cx'))).toBeGreaterThan(120)
    expect(screen.getByTestId('sentiment-label').textContent).toContain('bullish')
  })

  it('places the marker before midpoint for a bearish score', () => {
    render(<SentimentGauge sentiment={S({ score: -0.6, label: 'bearish' })} />)
    expect(Number(screen.getByTestId('sentiment-marker').getAttribute('cx'))).toBeLessThan(120)
  })

  it('shows an empty state when has_data is false', () => {
    render(<SentimentGauge sentiment={S({ has_data: false })} />)
    expect(screen.getByTestId('sentiment-empty')).toBeInTheDocument()
  })
})
