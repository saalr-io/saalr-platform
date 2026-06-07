import type { Strategy } from '../../lib/strategies'

export function StrategyPicker({
  strategies, value, onChange,
}: {
  strategies: Strategy[]; value: string; onChange: (id: string) => void
}) {
  if (strategies.length === 0) {
    return (
      <p className="text-sm text-txtFaint" data-testid="no-strategies">
        No saved strategies yet — <a href="/app/strategies" className="text-accent underline">build and save one</a> first.
      </p>
    )
  }
  return (
    <label className="flex items-center gap-2 text-xs text-txtDim">
      Strategy
      <select data-testid="bt-strategy" value={value} onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-line bg-panel px-2 py-2 font-mono text-xs text-txt">
        <option value="">Select…</option>
        {strategies.map((s) => <option key={s.strategy_id} value={s.strategy_id}>{s.name}</option>)}
      </select>
    </label>
  )
}
