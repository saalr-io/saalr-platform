import type React from 'react'
import { useState, useRef, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useRegime } from '../features/ideas/hooks'
import { usePaperTradeStrategy } from '../features/portfolio/usePaperTrade'
import { useCompleteStep } from '../features/onboarding/hooks'
import { buildTemplate } from '../lib/strategies'

function defaultExpiry(): string {
  const d = new Date()
  d.setDate(d.getDate() + 35)
  return d.toISOString().slice(0, 10)
}

type FlowStep = 'ticker' | 'regime' | 'done'

export function Start() {
  const [flowStep, setFlowStep] = useState<FlowStep>('ticker')
  const [input, setInput] = useState('')
  const [ticker, setTicker] = useState<string | null>(null)
  const complete = useCompleteStep()
  const regimeQ = useRegime(ticker)
  const paper = usePaperTradeStrategy()
  const seeRegimeFired = useRef(false)
  const paperTradeFired = useRef(false)

  const data = regimeQ.data
  const topReco = data?.recommendations?.[0] ?? null

  // When we enter the regime step and data is available, fire see_regime once
  useEffect(() => {
    if (flowStep === 'regime' && !seeRegimeFired.current) {
      seeRegimeFired.current = true
      complete.mutate('see_regime')
    }
  }, [flowStep, complete])

  function handleSeeRegime(e: React.FormEvent) {
    e.preventDefault()
    const t = input.trim().toUpperCase()
    if (!t) return
    setTicker(t)
    setFlowStep('regime')
  }

  async function handlePaperTrade() {
    if (!data || !topReco) return
    try {
      const config = await buildTemplate(topReco.template_key, {
        underlying: data.ticker,
        expiry: defaultExpiry(),
        atm_strike: data.regime.last_close,
      })
      paper.mutate(config, {
        onSuccess: () => {
          if (!paperTradeFired.current) {
            paperTradeFired.current = true
            complete.mutate('paper_trade')
          }
          setFlowStep('done')
        },
      })
    } catch {
      // ignore build errors — button stays enabled
    }
  }

  if (flowStep === 'ticker') {
    return (
      <div className="animate-fadeUp space-y-6" data-testid="start-step-ticker">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">// Get Started</p>
          <h2 className="mt-1 text-xl font-semibold tracking-tight">Welcome — let's make your first trade idea</h2>
          <p className="mt-1 text-sm text-txtDim">Enter a ticker to see its current market regime and a top strategy recommendation.</p>
        </div>
        <form onSubmit={handleSeeRegime} className="flex items-center gap-2">
          <input
            data-testid="start-ticker-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ticker (e.g. AAPL)"
            className="rounded-lg border border-line bg-panel px-3 py-2 font-mono text-sm uppercase text-txt"
            autoFocus
          />
          <button
            data-testid="start-see-regime"
            type="submit"
            className="rounded-md bg-accent px-4 py-2 text-xs font-medium text-canvas hover:opacity-90"
          >
            See regime
          </button>
        </form>
      </div>
    )
  }

  if (flowStep === 'regime') {
    return (
      <div className="animate-fadeUp space-y-6" data-testid="start-step-regime">
        <div>
          <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">// Step 2 of 3</p>
          <h2 className="mt-1 text-xl font-semibold tracking-tight">
            {ticker} — Market Regime
          </h2>
        </div>

        {regimeQ.isLoading && (
          <p className="text-sm text-txtDim">Reading the tape…</p>
        )}

        {regimeQ.isError && (
          <p className="text-sm text-neg">Couldn't analyze that ticker. Try another.</p>
        )}

        {data && (
          <div className="space-y-4">
            <div className="rounded-lg border border-line bg-panel p-4">
              <p className="font-mono text-xs text-txtFaint uppercase tracking-wide">Regime</p>
              <p className="mt-1 text-sm font-medium text-txt">{data.regime.headline}</p>
            </div>

            {topReco && (
              <div className="rounded-lg border border-line bg-panel p-4 space-y-2">
                <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-txtFaint">Top recommendation</p>
                <p className="text-sm font-medium text-txt">{topReco.name}</p>
                <p className="text-[11px] leading-snug text-txtDim">{topReco.rationale}</p>
                <button
                  data-testid="start-paper-trade"
                  type="button"
                  onClick={handlePaperTrade}
                  disabled={paper.isPending}
                  className="rounded-md bg-accent px-4 py-1.5 text-xs font-medium text-canvas hover:opacity-90 disabled:opacity-40"
                >
                  {paper.isPending ? 'Placing…' : 'Paper-trade this'}
                </button>
              </div>
            )}

            {!topReco && !regimeQ.isLoading && (
              <div className="space-y-3">
                <p className="text-sm text-txtDim">No recommendations available for this regime.</p>
                <Link
                  data-testid="start-paper-trade"
                  to="/portfolio"
                  className="inline-block rounded-md border border-line px-4 py-1.5 text-xs text-txtDim hover:text-txt"
                >
                  Go to Portfolio →
                </Link>
              </div>
            )}
          </div>
        )}
      </div>
    )
  }

  // flowStep === 'done'
  return (
    <div className="animate-fadeUp space-y-6" data-testid="start-step-done">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">// All set!</p>
        <h2 className="mt-1 text-xl font-semibold tracking-tight">Paper trade placed</h2>
        <p className="mt-1 text-sm text-txtDim">
          You've completed the activation flow. Track your paper trade in the Portfolio.
        </p>
      </div>
      <Link
        to="/portfolio"
        className="inline-block rounded-md bg-accent px-5 py-2 text-sm font-medium text-canvas hover:opacity-90"
      >
        View Portfolio →
      </Link>
    </div>
  )
}
