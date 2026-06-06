import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { useVolForecast, useSentiment, usePriceForecast, useMonteCarlo } from '../features/models/hooks'
import { ForecastPanel } from '../features/models/ForecastPanel'
import { SentimentGauge } from '../features/models/SentimentGauge'
import { MonteCarloPanel } from '../features/models/MonteCarloPanel'
import { PriceForecastPanel } from '../features/models/PriceForecastPanel'
import { SelectedStrategy } from '../features/strategies/SelectedStrategy'
import { ModelsGate } from '../features/models/ModelsGate'
import { TemplatePicker } from '../features/strategies/TemplatePicker'
import { EntitlementError } from '../lib/models'
import type { StrategyConfig } from '../lib/strategies'

const HORIZONS = [10, 20, 30]

function forecastError(err: unknown): string | null {
  if (!err) return null
  const code = (err as Error).message
  if (code === 'INSUFFICIENT_HISTORY') return 'Not enough price history (need 250+ trading days).'
  if (code === 'RESOURCE_NOT_FOUND') return 'Unknown ticker.'
  return 'Something went wrong — try again.'
}

function mcError(err: unknown): string | null {
  if (!err) return null
  const code = (err as Error).message
  if (code === 'VALIDATION_NO_EXPIRY') return 'Pick a template with an option expiry in the future.'
  if (code === 'INSUFFICIENT_HISTORY') return 'Not enough price history to estimate volatility (need 250+ trading days).'
  return 'Something went wrong — try again.'
}

export function Models() {
  const { me } = useAuth()
  const entitled = me?.entitlements?.ml_forecast === true

  const [tab, setTab] = useState<'insights' | 'montecarlo'>('insights')
  const [input, setInput] = useState('')
  const [ticker, setTicker] = useState('')
  const [horizon, setHorizon] = useState(10)

  const forecastQ = useVolForecast(entitled ? ticker : '', horizon, entitled)
  const sentimentQ = useSentiment(entitled ? ticker : '', entitled)
  const priceQ = usePriceForecast(entitled ? ticker : '', horizon, entitled)

  const [underlying, setUnderlying] = useState('')
  const [expiry, setExpiry] = useState('')
  const [atmStrike, setAtmStrike] = useState('')
  const [config, setConfig] = useState<StrategyConfig | null>(null)
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [paths, setPaths] = useState('10000')

  function clearSelection() {
    setConfig(null)
    setSelectedKey(null)
  }
  const [useSentimentDrift, setUseSentimentDrift] = useState(false)
  const mc = useMonteCarlo()

  if (!entitled) return <ModelsGate />
  if (
    forecastQ.error instanceof EntitlementError ||
    sentimentQ.error instanceof EntitlementError ||
    priceQ.error instanceof EntitlementError ||
    mc.error instanceof EntitlementError
  ) {
    return <ModelsGate />
  }

  function load() {
    const t = input.trim().toUpperCase()
    if (t) setTicker(t)
  }

  function runMc() {
    if (!config) return
    mc.mutate({ config, paths: parseInt(paths, 10) || 10000, use_sentiment: useSentimentDrift })
  }

  const fcErr = forecastError(forecastQ.error)
  const sentErr = forecastError(sentimentQ.error)
  const mcErrMsg = mcError(mc.error)
  const strike = parseFloat(atmStrike)
  const canPickTemplate = !!underlying.trim() && !!expiry && isFinite(strike) && strike > 0

  return (
    <div className="animate-fadeUp space-y-5">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">// Models</p>
        <h2 className="mt-1 text-xl font-semibold tracking-tight">Forecasts &amp; simulation</h2>
      </div>

      <div className="flex gap-2 border-b border-line">
        <button data-testid="tab-insights" onClick={() => setTab('insights')}
          className={`px-3 py-2 text-xs ${tab === 'insights' ? 'border-b-2 border-accent text-txt' : 'text-txtDim'}`}>Insights</button>
        <button data-testid="tab-montecarlo" onClick={() => setTab('montecarlo')}
          className={`px-3 py-2 text-xs ${tab === 'montecarlo' ? 'border-b-2 border-accent text-txt' : 'text-txtDim'}`}>Monte-Carlo</button>
      </div>

      {tab === 'insights' ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <input data-testid="ticker-input" value={input}
              onChange={(e) => setInput(e.target.value.toUpperCase().replace(/[^A-Z]/g, ''))}
              onKeyDown={(e) => { if (e.key === 'Enter') load() }}
              placeholder="e.g. AAPL" maxLength={8}
              className="w-32 rounded-lg border border-line bg-canvas px-3 py-2 font-mono text-sm uppercase tracking-wider text-txt placeholder:text-txtFaint focus:border-accent focus:outline-none" />
            <select data-testid="horizon-select" value={horizon} onChange={(e) => setHorizon(Number(e.target.value))}
              className="rounded-lg border border-line bg-panel px-2 py-2 font-mono text-xs text-txt">
              {HORIZONS.map((h) => <option key={h} value={h}>{h}d</option>)}
            </select>
            <button data-testid="ticker-load" onClick={load}
              className="rounded-lg bg-accent/20 px-4 py-2 text-xs text-accent transition hover:bg-accent/30">Load</button>
          </div>

          {(forecastQ.isLoading || sentimentQ.isLoading) && ticker && (
            <div className="animate-pulse rounded-lg border border-line bg-panel2 py-16" data-testid="models-loading" />
          )}
          {fcErr && ticker && <p className="text-sm text-neg" data-testid="forecast-error">{fcErr}</p>}
          {sentErr && ticker && <p className="text-sm text-neg" data-testid="sentiment-error">{sentErr}</p>}

          {(forecastQ.data || sentimentQ.data) && (
            <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
              {forecastQ.data && <ForecastPanel forecast={forecastQ.data} />}
              {sentimentQ.data && <SentimentGauge sentiment={sentimentQ.data} />}
            </div>
          )}
          {priceQ.data && <PriceForecastPanel forecast={priceQ.data} />}
          {priceQ.isLoading && ticker && (
            <div className="animate-pulse rounded-lg border border-line bg-panel2 py-16" data-testid="price-loading" />
          )}
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid gap-3 rounded-lg border border-line bg-panel p-4 md:grid-cols-4">
            <input data-testid="mc-underlying" value={underlying}
              onChange={(e) => { setUnderlying(e.target.value.toUpperCase().replace(/[^A-Z]/g, '')); clearSelection() }}
              placeholder="Underlying" className="rounded border border-line bg-canvas px-3 py-2 font-mono text-xs uppercase text-txt placeholder:text-txtFaint" />
            <input data-testid="mc-expiry" type="date" value={expiry} onChange={(e) => { setExpiry(e.target.value); clearSelection() }}
              className="rounded border border-line bg-canvas px-3 py-2 font-mono text-xs text-txt" />
            <input data-testid="mc-strike" value={atmStrike}
              onChange={(e) => { setAtmStrike(e.target.value.replace(/[^0-9.]/g, '')); clearSelection() }}
              placeholder="ATM strike" className="rounded border border-line bg-canvas px-3 py-2 font-mono text-xs text-txt placeholder:text-txtFaint" />
            <input data-testid="mc-paths" value={paths}
              onChange={(e) => setPaths(e.target.value.replace(/[^0-9]/g, ''))}
              placeholder="Paths" className="rounded border border-line bg-canvas px-3 py-2 font-mono text-xs text-txt placeholder:text-txtFaint" />
          </div>

          {canPickTemplate ? (
            <TemplatePicker underlying={underlying} expiry={expiry} atmStrike={strike}
              onApply={setConfig} onPick={setSelectedKey} selectedKey={selectedKey ?? undefined} />
          ) : (
            <p className="text-xs text-txtFaint" data-testid="mc-need-inputs">Enter an underlying, expiry, and ATM strike to pick a template.</p>
          )}

          {config && (
            <div className="space-y-3">
              <SelectedStrategy config={config} onChange={clearSelection} templateKey={selectedKey ?? undefined} />
              <div className="flex flex-wrap items-center gap-3">
                <label className="flex items-center gap-2 text-xs text-txtDim">
                  <input data-testid="mc-use-sentiment" type="checkbox" checked={useSentimentDrift} onChange={(e) => setUseSentimentDrift(e.target.checked)} />
                  Apply sentiment drift
                </label>
                <button data-testid="mc-run" onClick={runMc} disabled={mc.isPending}
                  className="rounded-md bg-accent px-4 py-2 text-xs font-medium text-canvas transition hover:opacity-90 disabled:opacity-40">
                  {mc.isPending ? 'Simulating…' : 'Run simulation'}
                </button>
              </div>
            </div>
          )}

          {mcErrMsg && <p className="text-sm text-neg" data-testid="mc-error">{mcErrMsg}</p>}
          {mc.data && <MonteCarloPanel result={mc.data} />}
        </div>
      )}
    </div>
  )
}
