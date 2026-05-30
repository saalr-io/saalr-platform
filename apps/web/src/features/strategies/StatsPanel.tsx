import type { AnalyzeResult } from '../../lib/strategies'

function Card({ label, value, tone, testid }: { label: string; value: string; tone?: 'pos' | 'neg'; testid: string }) {
  const color = tone === 'pos' ? 'text-pos' : tone === 'neg' ? 'text-red-400' : 'text-txt'
  return (
    <div className="flex-1 rounded-md border border-line bg-panel/60 p-2 text-center" data-testid={testid}>
      <div className="font-mono text-[9px] uppercase tracking-wider text-txtFaint">{label}</div>
      <div className={`text-sm ${color}`}>{value}</div>
    </div>
  )
}

export function StatsPanel({ result }: { result: AnalyzeResult }) {
  const maxP = result.unbounded_profit ? 'Unbounded' : result.max_profit?.toFixed(0) ?? '—'
  const maxL = result.unbounded_loss ? 'Unbounded' : result.max_loss?.toFixed(0) ?? '—'
  const g = result.net_greeks
  const pop = result.probability_of_profit?.pop
  return (
    <div>
      <div className="flex gap-2">
        <Card label="Max Profit" value={maxP} tone="pos" testid="stat-max-profit" />
        <Card label="Max Loss" value={maxL} tone="neg" testid="stat-max-loss" />
        <Card label="Breakeven" value={result.breakevens.map((b) => b.toFixed(1)).join(', ') || '—'} testid="stat-be" />
        <Card label="Net Premium" value={result.net_premium.toFixed(0)} testid="stat-net" />
        {pop !== undefined && pop !== null && (
          <Card label="POP*" value={`${Math.round(pop * 100)}%`} testid="stat-pop" />
        )}
        {g && (
          <div className="flex-1 rounded-md border border-line bg-panel/60 p-2 text-center" data-testid="stat-greeks">
            <div className="font-mono text-[9px] uppercase tracking-wider text-txtFaint">Δ / Θ / V</div>
            <div className="text-xs text-txt">{g.delta.toFixed(0)} / {g.theta.toFixed(0)} / {g.vega.toFixed(0)}</div>
          </div>
        )}
      </div>
      {!g && (
        <div className="mt-2 text-[11px] text-txtFaint" data-testid="upgrade-hint">
          Upgrade to Pro for live Greeks, probability of profit, and the target-date curve.
        </div>
      )}
      {result.probability_of_profit?.approximate && (
        <div className="mt-1 font-mono text-[9px] text-txtFaint">* POP approximate (lognormal).</div>
      )}
    </div>
  )
}
