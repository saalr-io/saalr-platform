import type { BacktestStatus as Status } from '../../lib/backtests'

export function BacktestStatus({ status, estSeconds, error }: { status: Status; estSeconds: number; error: string | null }) {
  if (status === 'failed') {
    return <p data-testid="bt-error" className="text-sm text-neg">Backtest failed: {error ?? 'unknown error'}</p>
  }
  return (
    <div data-testid="bt-running" className="flex items-center gap-3 rounded-lg border border-line bg-panel2 px-4 py-6">
      <span className="h-2 w-2 animate-pulse rounded-full bg-accent" />
      <span className="text-sm text-txtDim">Running backtest… ≈ {estSeconds}s</span>
    </div>
  )
}
