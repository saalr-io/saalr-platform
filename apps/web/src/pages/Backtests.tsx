import { useState } from 'react'
import { useStrategies } from '../features/strategies/hooks'
import { useCreateBacktest, useBacktest } from '../features/backtests/hooks'
import { StrategyPicker } from '../features/backtests/StrategyPicker'
import { BacktestForm } from '../features/backtests/BacktestForm'
import { EquityCurve } from '../features/backtests/EquityCurve'
import { MetricsPanel } from '../features/backtests/MetricsPanel'
import { BacktestStatus } from '../features/backtests/BacktestStatus'
import type { BacktestRequestBody } from '../lib/backtests'

export function Backtests() {
  const strategiesQ = useStrategies()
  const strategies = strategiesQ.data?.strategies ?? []
  const [strategyId, setStrategyId] = useState('')
  const [capital, setCapital] = useState(100000)
  const create = useCreateBacktest()
  const [backtestId, setBacktestId] = useState<string | null>(null)
  const runQ = useBacktest(backtestId)
  const run = runQ.data

  function onSubmit(body: BacktestRequestBody, key: string) {
    if (!strategyId) return
    setCapital(body.initial_capital)
    setBacktestId(null)
    create.mutate({ strategyId, body, key }, { onSuccess: (r) => setBacktestId(r.backtest_id) })
  }

  const status = run?.status ?? (create.isPending ? 'queued' : null)
  const estSeconds = create.data?.estimated_duration_seconds ?? 0

  return (
    <div className="animate-fadeUp space-y-5">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">// Backtest</p>
        <h2 className="mt-1 text-xl font-semibold tracking-tight">Historical backtest</h2>
      </div>

      <StrategyPicker strategies={strategies} value={strategyId} onChange={setStrategyId} />
      {strategies.length > 0 && (
        <BacktestForm disabled={!strategyId} pending={create.isPending} onSubmit={onSubmit} />
      )}

      {create.isError && <p className="text-sm text-neg">Couldn&apos;t start the backtest — try again.</p>}

      {status && status !== 'succeeded' && (
        <BacktestStatus
          status={status}
          estSeconds={estSeconds}
          error={run?.error?.message ?? null}
        />
      )}

      {run?.status === 'succeeded' && run.metrics && run.equity_series && (
        <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
          <EquityCurve series={run.equity_series} initialCapital={capital} />
          <MetricsPanel metrics={run.metrics} finalEquity={run.equity_series[run.equity_series.length - 1].equity} approximate model="bsm" volLookback={20} />
        </div>
      )}
    </div>
  )
}
