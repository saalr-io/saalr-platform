import type { Leg, StrategyConfig } from '../../lib/strategies'

function LegRow({ leg, i }: { leg: Leg; i: number }) {
  const sideClass = (side: 'BUY' | 'SELL') => (side === 'BUY' ? 'text-pos' : 'text-neg')
  if (leg.kind === 'option') {
    return (
      <li data-testid={`mc-leg-${i}`} className="flex items-center gap-2">
        <span className={`w-10 font-semibold ${sideClass(leg.side)}`}>{leg.side}</span>
        <span className="w-10 text-txt">{leg.option_type}</span>
        <span className="tnum w-14 text-txt">{leg.strike}</span>
        <span className="text-txtFaint">×{leg.qty}</span>
        <span className="ml-auto text-[11px] text-txtFaint">{leg.expiry}</span>
      </li>
    )
  }
  if (leg.kind === 'equity') {
    return (
      <li data-testid={`mc-leg-${i}`} className="flex items-center gap-2">
        <span className={`w-10 font-semibold ${sideClass(leg.side)}`}>{leg.side}</span>
        <span className="text-txt">{leg.qty} shares</span>
      </li>
    )
  }
  return (
    <li data-testid={`mc-leg-${i}`} className="flex items-center gap-2">
      <span className="text-txtDim">cash collateral</span>
      <span className="tnum text-txt">${leg.amount.toLocaleString()}</span>
    </li>
  )
}

export function SelectedStrategy({ config, onChange }: { config: StrategyConfig; onChange: () => void }) {
  return (
    <div className="rounded-lg border border-line bg-panel p-3" data-testid="mc-selected">
      <div className="mb-2 flex items-center justify-between">
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-txtFaint">
          Selected strategy · <span className="text-txt">{config.underlying}</span>
        </p>
        <button
          type="button"
          data-testid="mc-change"
          onClick={onChange}
          className="text-[11px] text-accent transition-colors hover:underline"
        >
          Change
        </button>
      </div>
      <ul className="space-y-1 font-mono text-xs">
        {config.legs.map((leg, i) => <LegRow key={i} leg={leg} i={i} />)}
      </ul>
    </div>
  )
}
