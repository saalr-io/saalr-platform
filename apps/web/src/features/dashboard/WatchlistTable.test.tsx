import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { WatchlistTable, type WatchRow } from './WatchlistTable'

const R = (over: Partial<WatchRow> = {}): WatchRow => ({
  symbol: 'AAPL', forecastPct: 22.5, sentimentLabel: 'bullish', loading: false, ...over,
})

describe('WatchlistTable', () => {
  it('renders a row with the vol forecast and sentiment chip', () => {
    render(<MemoryRouter><WatchlistTable rows={[R()]} entitled={true} onAddSymbol={vi.fn()} /></MemoryRouter>)
    const row = screen.getByTestId('watch-AAPL')
    expect(row.textContent).toContain('22.5%')
    expect(row.textContent).toContain('bullish')
  })

  it('shows an upgrade hint when not entitled', () => {
    render(<MemoryRouter><WatchlistTable rows={[]} entitled={false} onAddSymbol={vi.fn()} /></MemoryRouter>)
    expect(screen.getByTestId('upgrade-hint')).toBeInTheDocument()
  })

  it('lets the user add a symbol from the empty state', () => {
    const onAdd = vi.fn()
    render(<MemoryRouter><WatchlistTable rows={[]} entitled={true} onAddSymbol={onAdd} /></MemoryRouter>)
    fireEvent.change(screen.getByTestId('watchlist-add-input'), { target: { value: 'TSLA' } })
    fireEvent.click(screen.getByTestId('watchlist-add-btn'))
    expect(onAdd).toHaveBeenCalledWith('TSLA')
  })
})
