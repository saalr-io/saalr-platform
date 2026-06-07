import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, Link } from 'react-router-dom'
import { usePaperTradeStrategy } from '../features/portfolio/usePaperTrade'
import { useCompleteStep } from '../features/onboarding/hooks'
import { LegEditor } from '../features/strategies/LegEditor'
import { TemplatePicker } from '../features/strategies/TemplatePicker'
import { SelectedStrategy } from '../features/strategies/SelectedStrategy'
import { SavedList } from '../features/strategies/SavedList'
import { PayoffChart } from '../features/strategies/PayoffChart'
import { StatsPanel } from '../features/strategies/StatsPanel'
import { useAnalyze, useCreateStrategy } from '../features/strategies/hooks'
import { EntitlementError, type AnalyzeResult, type StrategyConfig } from '../lib/strategies'

type Tab = 'ready' | 'build' | 'saved'

const INITIAL: StrategyConfig = {
  underlying: 'AAPL',
  legs: [
    { kind: 'option', option_type: 'CALL', side: 'BUY', strike: 100, expiry: '2026-12-18', qty: 1, entry_price: 6 },
    { kind: 'option', option_type: 'CALL', side: 'SELL', strike: 110, expiry: '2026-12-18', qty: 1, entry_price: 2 },
  ],
}

function atmStrike(c: StrategyConfig): number {
  const s = c.legs.flatMap((l) => (l.kind === 'option' ? [l.strike] : []))
  return s.length ? s.reduce((a, b) => a + b, 0) / s.length : 100
}
function firstExpiry(c: StrategyConfig): string {
  const o = c.legs.find((l) => l.kind === 'option')
  return o && o.kind === 'option' ? o.expiry : '2026-12-18'
}

export function Strategies() {
  const [tab, setTab] = useState<Tab>('build')
  const [config, setConfig] = useState<StrategyConfig>(INITIAL)
  const [live, setLive] = useState(false)
  const [targetDate, setTargetDate] = useState('')
  const [result, setResult] = useState<AnalyzeResult | null>(null)
  const [needUpgrade, setNeedUpgrade] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [readyKey, setReadyKey] = useState<string | null>(null)
  const location = useLocation()
  const navigate = useNavigate()
  useEffect(() => {
    const incoming = (location.state as { config?: StrategyConfig } | null)?.config
    if (incoming) {
      setConfig(incoming)
      setTab('build')
      // Consume the handoff: clear history state so a back-nav re-mount doesn't
      // clobber the user's subsequent edits with the original Apply payload.
      navigate('.', { replace: true, state: {} })
    }
  }, [location.state, navigate])
  const analyze = useAnalyze()
  const create = useCreateStrategy()
  const paper = usePaperTradeStrategy()
  const complete = useCompleteStep()
  const buildStrategyFired = useRef(false)
  const paperTradeFired = useRef(false)

  const missingPrices =
    !live && config.legs.some((l) => l.kind === 'option' && (l.entry_price === null || l.entry_price === undefined))

  function runAnalyze() {
    setNeedUpgrade(false)
    setErrorMsg(null)
    analyze.mutate(
      { config, live, target_date: targetDate || undefined },
      {
        onSuccess: (r) => setResult(r),
        onError: (e) => {
          if (e instanceof EntitlementError) setNeedUpgrade(true)
          else setErrorMsg(e.message || 'Analysis failed — please try again.')
        },
      },
    )
  }

  function save() {
    setSaved(false)
    create.mutate(
      { name: `${config.underlying} strategy`, config },
      {
        onSuccess: () => {
          setSaved(true)
          if (!buildStrategyFired.current) {
            buildStrategyFired.current = true
            complete.mutate('build_strategy')
          }
        },
        onError: (e) => setErrorMsg(e.message || 'Save failed.'),
      },
    )
  }

  return (
    <div className="animate-fadeUp space-y-4">
      <div className="flex items-baseline gap-3">
        <h2 className="text-xl font-semibold tracking-tight">Strategy Builder</h2>
        <span className="font-mono text-[10px] uppercase tracking-wider text-txtFaint">payoff · greeks · POP</span>
      </div>

      {needUpgrade && (
        <div className="rounded-md border border-yellow-700/40 bg-yellow-900/10 px-3 py-2 text-xs text-yellow-300" data-testid="upgrade-banner">
          Live Greeks, probability of profit, and the target-date curve require a Pro plan. Showing the expiry payoff from entered prices.
        </div>
      )}

      {errorMsg && (
        <div className="rounded-md border border-red-700/40 bg-red-900/10 px-3 py-2 text-xs text-red-300" data-testid="error-banner">
          {errorMsg}
        </div>
      )}

      {result && (
        <>
          <PayoffChart expirationCurve={result.expiration_curve} targetDateCurve={result.target_date_curve}
                       breakevens={result.breakevens} spot={result.spot} />
          <StatsPanel result={result} />
        </>
      )}

      <div className="rounded-lg border border-line bg-panel/30 p-3">
        <div className="mb-3 flex gap-2">
          {(['ready', 'build', 'saved'] as Tab[]).map((t) => (
            <button key={t} data-testid={`tab-${t}`} onClick={() => setTab(t)}
                    className={`rounded px-3 py-1 text-xs ${tab === t ? 'bg-pos/20 text-pos' : 'text-txtDim hover:text-txt'}`}>
              {t === 'ready' ? 'Ready-made' : t === 'build' ? 'Build your own' : 'Saved'}
            </button>
          ))}
        </div>

        {tab === 'ready' && (
          <div className="space-y-3">
            <TemplatePicker underlying={config.underlying} expiry={firstExpiry(config)} atmStrike={atmStrike(config)}
                            selectedKey={readyKey ?? undefined} onPick={setReadyKey} onApply={setConfig} />
            {readyKey && (
              <div className="space-y-2" data-testid="ready-selected">
                <SelectedStrategy config={config} templateKey={readyKey ?? undefined} />
                <button type="button" data-testid="ready-tweak" onClick={() => setTab('build')}
                        className="rounded-md bg-accent px-4 py-1.5 text-xs font-medium text-canvas transition hover:opacity-90">
                  Tweak in builder →
                </button>
              </div>
            )}
          </div>
        )}
        {tab === 'build' && <LegEditor config={config} onChange={setConfig} />}
        {tab === 'saved' && <SavedList onLoad={(s) => { setConfig(s.config); setTab('build') }} />}

        <div className="mt-3 flex items-center gap-3">
          <label className="flex items-center gap-1 text-[11px] text-txtDim">
            <input type="checkbox" data-testid="live-toggle" checked={live} onChange={(e) => setLive(e.target.checked)} /> live
          </label>
          <label className="flex items-center gap-1 text-[11px] text-txtDim">
            Target date
            <input type="date" className="rounded border border-line bg-canvas px-2 py-1 text-xs text-txt"
                   aria-label="Target date" data-testid="target-date" value={targetDate}
                   onChange={(e) => setTargetDate(e.target.value)} disabled={!live} />
          </label>
          <button data-testid="analyze-btn" onClick={runAnalyze} disabled={analyze.isPending}
                  className="rounded bg-pos/20 px-4 py-1 text-xs text-pos hover:bg-pos/30">
            {analyze.isPending ? 'Analyzing…' : 'Analyze'}
          </button>
          <button data-testid="save-btn" onClick={save} disabled={create.isPending}
                  className="rounded border border-line px-4 py-1 text-xs text-txtDim hover:text-txt">
            {create.isPending ? 'Saving…' : 'Save'}
          </button>
          <button data-testid="paper-trade-btn" onClick={() => paper.mutate(config, {
            onSuccess: () => {
              if (!paperTradeFired.current) {
                paperTradeFired.current = true
                complete.mutate('paper_trade')
              }
            },
          })} disabled={paper.isPending}
                  className="rounded border border-line px-4 py-1 text-xs text-txtDim hover:text-txt disabled:opacity-40">
            {paper.isPending ? 'Placing…' : 'Paper trade'}
          </button>
          {saved && <span className="text-xs text-pos" data-testid="saved-ok">Saved ✓</span>}
          {paper.data && (
            <span className="text-xs text-txtDim" data-testid="paper-trade-result">
              Placed {paper.data.placed}{paper.data.rejected > 0 ? ` · ${paper.data.rejected} rejected` : ''} ·{' '}
              <Link to="/portfolio" className="text-accent hover:underline">Portfolio →</Link>
            </span>
          )}
        </div>
        {missingPrices && (
          <div className="mt-2 text-[11px] text-txtFaint" data-testid="price-hint">
            Some option legs have no entry price — the expiry payoff treats those as 0. Enter prices, or enable live (Pro) to auto-fill from the market.
          </div>
        )}
      </div>
    </div>
  )
}
