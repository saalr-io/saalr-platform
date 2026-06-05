import { useState } from 'react'
import type { BacktestRequestBody } from '../../lib/backtests'

function isoYearsAgo(years: number): string {
  const d = new Date()
  d.setFullYear(d.getFullYear() - years)
  return d.toISOString().slice(0, 10)
}

export function BacktestForm({
  disabled, pending, onSubmit,
}: {
  disabled: boolean; pending: boolean; onSubmit: (body: BacktestRequestBody, key: string) => void
}) {
  const [start, setStart] = useState(isoYearsAgo(2))
  const [end, setEnd] = useState(new Date().toISOString().slice(0, 10))
  const [capital, setCapital] = useState('100000')
  const [costs, setCosts] = useState(true)

  const valid = !!start && !!end && end > start
  function submit() {
    if (!valid) return
    onSubmit(
      { start_date: start, end_date: end, initial_capital: parseInt(capital, 10) || 100000, include_costs: costs },
      crypto.randomUUID(),
    )
  }
  return (
    <div className="flex flex-wrap items-end gap-3 rounded-lg border border-line bg-panel p-4">
      <label className="text-xs text-txtDim">Start
        <input data-testid="bt-start" type="date" value={start} onChange={(e) => setStart(e.target.value)}
          className="ml-2 rounded border border-line bg-canvas px-2 py-1 font-mono text-xs text-txt" /></label>
      <label className="text-xs text-txtDim">End
        <input data-testid="bt-end" type="date" value={end} onChange={(e) => setEnd(e.target.value)}
          className="ml-2 rounded border border-line bg-canvas px-2 py-1 font-mono text-xs text-txt" /></label>
      <label className="text-xs text-txtDim">Capital
        <input data-testid="bt-capital" value={capital} onChange={(e) => setCapital(e.target.value.replace(/[^0-9]/g, ''))}
          className="ml-2 w-28 rounded border border-line bg-canvas px-2 py-1 font-mono text-xs text-txt" /></label>
      <label className="flex items-center gap-2 text-xs text-txtDim">
        <input data-testid="bt-costs" type="checkbox" checked={costs} onChange={(e) => setCosts(e.target.checked)} /> Include costs
      </label>
      <button data-testid="bt-run" onClick={submit} disabled={disabled || pending || !valid}
        className="rounded-md bg-accent px-4 py-2 text-xs font-medium text-canvas transition hover:opacity-90 disabled:opacity-40">
        {pending ? "Running…" : "Run backtest"}
      </button>
    </div>
  )
}
