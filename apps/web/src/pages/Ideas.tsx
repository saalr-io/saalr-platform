import type React from 'react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useRegime } from '../features/ideas/hooks'
import { RegimePanel } from '../features/ideas/RegimePanel'
import { RecoCard } from '../features/ideas/RecoCard'
import { buildTemplate } from '../lib/strategies'
import { usePaperTradeStrategy } from '../features/portfolio/usePaperTrade'
import type { PaperState } from '../features/ideas/RecoCard'

function defaultExpiry(): string {
  const d = new Date()
  d.setDate(d.getDate() + 35)
  return d.toISOString().slice(0, 10)
}

export function Ideas() {
  const [input, setInput] = useState('')
  const [ticker, setTicker] = useState<string | null>(null)
  const [applyingKey, setApplyingKey] = useState<string | null>(null)
  const q = useRegime(ticker)
  const navigate = useNavigate()
  const paper = usePaperTradeStrategy()
  const [paperKey, setPaperKey] = useState<string | null>(null)
  const data = q.data

  function submit(e: React.FormEvent) {
    e.preventDefault()
    const t = input.trim().toUpperCase()
    if (t) setTicker(t)
  }

  async function paperTrade(key: string) {
    if (!data) return
    setPaperKey(key)
    try {
      const config = await buildTemplate(key, {
        underlying: data.ticker, expiry: defaultExpiry(), atm_strike: data.regime.last_close,
      })
      await paper.mutateAsync(config)
    } catch {
      setPaperKey(null)
    }
  }

  function paperStateFor(key: string): PaperState {
    if (paperKey !== key) return 'idle'
    if (paper.isPending) return 'pending'
    if (paper.data) return { placed: paper.data.placed, rejected: paper.data.rejected }
    return 'idle'
  }

  async function apply(key: string) {
    if (!data) return
    setApplyingKey(key)
    try {
      const config = await buildTemplate(key, {
        underlying: data.ticker, expiry: defaultExpiry(), atm_strike: data.regime.last_close,
      })
      navigate('/strategies', { state: { config } })
      // success unmounts this page; only reset the spinner if the build failed
    } catch {
      setApplyingKey(null)
    }
  }

  const recos = data?.recommendations ?? []

  return (
    <div className="animate-fadeUp space-y-5">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">// Trade Ideas</p>
        <h2 className="mt-1 text-xl font-semibold tracking-tight">Regime &amp; ideas</h2>
      </div>

      <form onSubmit={submit} className="flex items-center gap-2">
        <input
          data-testid="idea-ticker"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ticker (e.g. SPY)"
          className="rounded-lg border border-line bg-panel px-3 py-2 font-mono text-sm uppercase text-txt"
        />
        <button data-testid="idea-go" type="submit" className="rounded-md bg-accent px-4 py-2 text-xs font-medium text-canvas hover:opacity-90">
          Analyze
        </button>
      </form>

      {q.isLoading && <p data-testid="idea-loading" className="text-sm text-txtDim">Reading the tape…</p>}
      {q.isError && (
        <p data-testid="idea-error" className="text-sm text-neg">
          {String((q.error as Error).message) === "INSUFFICIENT_HISTORY"
            ? "Not enough price history for this ticker yet."
            : "Couldn't analyze that ticker."}
        </p>
      )}

      {data && (
        <div className="grid gap-5 lg:grid-cols-[1fr_1.1fr]">
          <RegimePanel regime={data.regime} />
          <div className="space-y-2">
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-txtFaint">Recommended for this regime</p>
            {recos.slice(0, 5).map((r) => (
              <RecoCard
                key={r.template_key}
                reco={r}
                onApply={apply}
                applying={applyingKey === r.template_key}
                onPaperTrade={paperTrade}
                paperState={paperStateFor(r.template_key)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
