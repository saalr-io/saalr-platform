import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { OrderTicket } from './OrderTicket'

describe('OrderTicket', () => {
  it('submits an equity market order with a key', () => {
    const onSubmit = vi.fn()
    render(<OrderTicket disabled={false} pending={false} error={null} lastResult={null} onSubmit={onSubmit} />)
    fireEvent.change(screen.getByTestId('ot-symbol'), { target: { value: 'SPY' } })
    fireEvent.change(screen.getByTestId('ot-qty'), { target: { value: '5' } })
    fireEvent.click(screen.getByTestId('ot-submit'))
    expect(onSubmit).toHaveBeenCalledTimes(1)
    const [draft, key] = onSubmit.mock.calls[0]
    expect(draft).toMatchObject({ symbol: 'SPY', side: 'BUY', qty: 5, order_type: 'market' })
    expect(draft.option_type).toBeUndefined()
    expect(typeof key).toBe('string')
  })

  it('adds limit_price and option fields when enabled', () => {
    const onSubmit = vi.fn()
    render(<OrderTicket disabled={false} pending={false} error={null} lastResult={null} onSubmit={onSubmit} />)
    fireEvent.change(screen.getByTestId('ot-symbol'), { target: { value: 'AAPL' } })
    fireEvent.change(screen.getByTestId('ot-qty'), { target: { value: '1' } })
    fireEvent.change(screen.getByTestId('ot-type'), { target: { value: 'limit' } })
    fireEvent.change(screen.getByTestId('ot-limit'), { target: { value: '12.5' } })
    fireEvent.click(screen.getByTestId('ot-options'))
    fireEvent.change(screen.getByTestId('ot-option-type'), { target: { value: 'CALL' } })
    fireEvent.change(screen.getByTestId('ot-strike'), { target: { value: '150' } })
    fireEvent.change(screen.getByTestId('ot-expiry'), { target: { value: '2026-12-18' } })
    fireEvent.click(screen.getByTestId('ot-submit'))
    const [draft] = onSubmit.mock.calls[0]
    expect(draft).toMatchObject({ order_type: 'limit', limit_price: 12.5, option_type: 'CALL', strike: 150, expiry: '2026-12-18' })
  })

  it('disables submit while pending', () => {
    render(<OrderTicket disabled={false} pending={true} error={null} lastResult={null} onSubmit={vi.fn()} />)
    expect(screen.getByTestId('ot-submit')).toBeDisabled()
  })

  it('shows an error message', () => {
    render(<OrderTicket disabled={false} pending={false} error="insufficient buying power" lastResult={null} onSubmit={vi.fn()} />)
    expect(screen.getByTestId('ot-error').textContent).toContain('insufficient buying power')
  })

  it('does not submit a limit order with an empty limit price', () => {
    const onSubmit = vi.fn()
    render(<OrderTicket disabled={false} pending={false} error={null} lastResult={null} onSubmit={onSubmit} />)
    fireEvent.change(screen.getByTestId('ot-symbol'), { target: { value: 'SPY' } })
    fireEvent.change(screen.getByTestId('ot-qty'), { target: { value: '1' } })
    fireEvent.change(screen.getByTestId('ot-type'), { target: { value: 'limit' } })
    fireEvent.click(screen.getByTestId('ot-submit'))
    expect(onSubmit).not.toHaveBeenCalled()
  })
})
