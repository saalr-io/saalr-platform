import type { BacktestMetrics } from '../../lib/backtests'

const pct = (v: number) => `${(v * 100).toFixed(1)}%`
const usd = (v: number) => `$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`

export function MetricsPanel({
  metrics, finalEquity, approximate, model, volLookback,
}: {
  metrics: BacktestMetrics; finalEquity: number; approximate: boolean; model: string; volLookback: number
}) {
  const tiles: { key: string; label: string; value: string; cls?: string; testid: string }[] = [
    { key: 'tr', label: 'Total return', value: pct(metrics.total_return), cls: metrics.total_return >= 0 ? 'text-pos' : 'text-neg', testid: 'mx-total-return' },
    { key: 'ar', label: 'Annualized', value: pct(metrics.annualized_return), testid: 'mx-annualized' },
    { key: 'sh', label: 'Sharpe', value: metrics.sharpe.toFixed(2), testid: 'mx-sharpe' },
    { key: 'so', label: 'Sortino', value: metrics.sortino.toFixed(2), testid: 'mx-sortino' },
    { key: 'dd', label: 'Max drawdown', value: pct(metrics.max_drawdown), cls: 'text-neg', testid: 'mx-maxdd' },
    { key: 'wr', label: 'Win rate', value: pct(metrics.win_rate), testid: 'mx-winrate' },
    { key: 'tc', label: 'Trades', value: String(metrics.trades), testid: 'mx-trades' },
    { key: 'ap', label: 'Avg trade P&L', value: usd(metrics.avg_trade_pnl), cls: metrics.avg_trade_pnl >= 0 ? 'text-pos' : 'text-neg', testid: 'mx-avgpnl' },
    { key: 'fe', label: 'Final equity', value: usd(finalEquity), testid: 'mx-final' },
  ]
  return (
    <div className="space-y-3 rounded-lg border border-line bg-panel p-4" data-testid="metrics-panel">
      <div className="grid grid-cols-3 gap-3">
        {tiles.map((t) => (
          <div key={t.key} className="rounded border border-lineSoft p-3">
            <p className="font-mono text-[10px] uppercase tracking-wider text-txtFaint">{t.label}</p>
            <p data-testid={t.testid} className={`tnum mt-1 text-lg font-semibold ${t.cls ?? 'text-txt'}`}>{t.value}</p>
          </div>
        ))}
      </div>
      {approximate && (
        <p className="font-mono text-[11px] text-txtFaint">
          model {model} · realized-vol IV · vol lookback {volLookback} · <span className="text-warn">approximate</span> (model-priced, not tick data)
        </p>
      )}
    </div>
  )
}
