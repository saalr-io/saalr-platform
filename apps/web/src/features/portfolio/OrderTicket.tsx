import { useState } from 'react'
import type { OrderCreate } from '../../lib/oms'

type Draft = Omit<OrderCreate, 'broker_account_id'>

interface Props {
  disabled: boolean
  pending: boolean
  error: string | null
  lastResult: string | null
  onSubmit: (draft: Draft, key: string) => void
}

const inputCls = 'rounded-lg border border-line bg-canvas px-3 py-2 text-xs text-txt placeholder:text-txtFaint focus:border-accent focus:outline-none'

export function OrderTicket({ disabled, pending, error, lastResult, onSubmit }: Props) {
  const [symbol, setSymbol] = useState('')
  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY')
  const [qty, setQty] = useState('')
  const [orderType, setOrderType] = useState<'market' | 'limit'>('market')
  const [limit, setLimit] = useState('')
  const [optionsOn, setOptionsOn] = useState(false)
  const [optionType, setOptionType] = useState<'CALL' | 'PUT'>('CALL')
  const [strike, setStrike] = useState('')
  const [expiry, setExpiry] = useState('')

  function submit() {
    const sym = symbol.trim().toUpperCase()
    const q = parseInt(qty, 10)
    if (!sym || !q) return
    const draft: Draft = { symbol: sym, side, qty: q, order_type: orderType, time_in_force: 'day' }
    if (orderType === 'limit') {
      const lp = parseFloat(limit)
      if (!isFinite(lp) || lp <= 0) return
      draft.limit_price = lp
    }
    if (optionsOn) {
      const st = parseFloat(strike)
      if (!isFinite(st) || st <= 0 || !expiry) return
      draft.option_type = optionType
      draft.strike = st
      draft.expiry = expiry
    }
    onSubmit(draft, crypto.randomUUID())
  }

  return (
    <div className="space-y-3 rounded-lg border border-line bg-panel p-4" data-testid="order-ticket">
      <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent">// Order ticket</p>

      <div className="flex gap-2">
        <input data-testid="ot-symbol" value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase().replace(/[^A-Z]/g, ''))}
          placeholder="Symbol" maxLength={8} className={`${inputCls} w-28 uppercase`} />
        <select data-testid="ot-side" value={side} onChange={(e) => setSide(e.target.value as 'BUY' | 'SELL')} className={inputCls}>
          <option value="BUY">Buy</option>
          <option value="SELL">Sell</option>
        </select>
        <input data-testid="ot-qty" value={qty} onChange={(e) => setQty(e.target.value.replace(/[^0-9]/g, ''))}
          placeholder="Qty" className={`${inputCls} w-20`} />
      </div>

      <div className="flex gap-2">
        <select data-testid="ot-type" value={orderType} onChange={(e) => setOrderType(e.target.value as 'market' | 'limit')} className={inputCls}>
          <option value="market">Market</option>
          <option value="limit">Limit</option>
        </select>
        {orderType === 'limit' && (
          <input data-testid="ot-limit" value={limit} onChange={(e) => setLimit(e.target.value)}
            placeholder="Limit price" className={`${inputCls} w-28`} />
        )}
      </div>

      <label className="flex items-center gap-2 text-xs text-txtDim">
        <input data-testid="ot-options" type="checkbox" checked={optionsOn} onChange={(e) => setOptionsOn(e.target.checked)} />
        Options leg
      </label>
      {optionsOn && (
        <div className="flex flex-wrap gap-2">
          <select data-testid="ot-option-type" value={optionType} onChange={(e) => setOptionType(e.target.value as 'CALL' | 'PUT')} className={inputCls}>
            <option value="CALL">Call</option>
            <option value="PUT">Put</option>
          </select>
          <input data-testid="ot-strike" value={strike} onChange={(e) => setStrike(e.target.value)} placeholder="Strike" className={`${inputCls} w-24`} />
          <input data-testid="ot-expiry" type="date" value={expiry} onChange={(e) => setExpiry(e.target.value)} className={inputCls} />
        </div>
      )}

      <button data-testid="ot-submit" onClick={submit} disabled={disabled || pending}
        className="w-full rounded-md bg-accent px-4 py-2 text-xs font-medium text-canvas transition hover:opacity-90 disabled:opacity-40">
        {pending ? "Submitting…" : disabled ? "Select an account" : "Place order"}
      </button>

      {error && <p data-testid="ot-error" className="text-[11px] text-neg">Rejected: {error}</p>}
      {lastResult && !error && <p data-testid="ot-result" className="text-[11px] text-pos">{lastResult}</p>}
    </div>
  )
}
