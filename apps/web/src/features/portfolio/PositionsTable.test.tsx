import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { PositionsTable, rowKey } from './PositionsTable'
import type { Position } from '../../lib/oms'

const P = (over: Partial<Position> = {}): Position => ({
  broker_account_id: 'a1', symbol: 'AAPL', option_type: null, strike: null, expiry: null,
  qty: 10, avg_entry_price: '150.00', ...over,
})

describe('PositionsTable', () => {
  it('formats an option instrument', () => {
    render(<PositionsTable positions={[P({ option_type: 'CALL', strike: '150', expiry: '2026-12-18' })]}
      confirmingId={null} closingId={null} onCloseRequest={vi.fn()} onCloseConfirm={vi.fn()} onCloseCancel={vi.fn()} />)
    expect(screen.getByText(/AAPL \$150 CALL 2026-12-18/)).toBeInTheDocument()
  })

  it('first Close click requests confirm; Yes confirms', () => {
    const onReq = vi.fn(); const onConfirm = vi.fn()
    const pos = P()
    const key = rowKey(pos)
    const { rerender } = render(<PositionsTable positions={[pos]} confirmingId={null} closingId={null}
      onCloseRequest={onReq} onCloseConfirm={onConfirm} onCloseCancel={vi.fn()} />)
    fireEvent.click(screen.getByTestId('close-btn'))
    expect(onReq).toHaveBeenCalledWith(key)
    expect(onConfirm).not.toHaveBeenCalled()
    rerender(<PositionsTable positions={[pos]} confirmingId={key} closingId={null}
      onCloseRequest={onReq} onCloseConfirm={onConfirm} onCloseCancel={vi.fn()} />)
    fireEvent.click(screen.getByTestId('close-yes'))
    expect(onConfirm).toHaveBeenCalledWith(pos)
  })

  it('shows Closing… and hides the confirm buttons while closingId matches', () => {
    const pos = P()
    const key = rowKey(pos)
    render(<PositionsTable positions={[pos]} confirmingId={key} closingId={key}
      onCloseRequest={vi.fn()} onCloseConfirm={vi.fn()} onCloseCancel={vi.fn()} />)
    expect(screen.getByText(/Closing…/)).toBeInTheDocument()
    expect(screen.queryByTestId('close-yes')).toBeNull()
  })

  it('shows an empty state', () => {
    render(<PositionsTable positions={[]} confirmingId={null} closingId={null}
      onCloseRequest={vi.fn()} onCloseConfirm={vi.fn()} onCloseCancel={vi.fn()} />)
    expect(screen.getByTestId('positions-empty')).toBeInTheDocument()
  })
})
