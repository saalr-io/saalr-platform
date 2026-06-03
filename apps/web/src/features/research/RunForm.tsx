import { useState } from 'react'
import { EntitlementError } from '../../lib/research'
import { useRunResearch } from './hooks'
import type { ResearchNote } from '../../lib/research'

// ── props ──────────────────────────────────────────────────────────────────

interface RunFormProps {
  onNote: (note: ResearchNote) => void
  onPending: (noteId: string) => void
  onPremiumRequired: () => void
}

// ── component ──────────────────────────────────────────────────────────────

export function RunForm({ onNote, onPending, onPremiumRequired }: RunFormProps) {
  const [ticker, setTicker] = useState('')
  const [refresh, setRefresh] = useState(false)
  const run = useRunResearch()

  // Inline error message derived from mutation error code
  function errorMessage(): string | null {
    if (!run.isError) return null
    const { error } = run
    const code = error instanceof EntitlementError ? error.code : error.message
    if (code === 'RESEARCH_BUDGET_EXCEEDED') return 'Monthly research budget reached.'
    if (code === 'RATE_LIMIT_RESEARCH_DAILY_EXCEEDED') return 'Daily limit of 10 research notes reached — try again tomorrow.'
    if (code === 'VALIDATION_INVALID_PARAMETER') return 'Enter a valid US ticker.'
    if (code === 'RESEARCH_ENQUEUE_FAILED') return "Couldn't start the run — try again."
    // Premium gate is handled by the page; surface nothing inline
    return null
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const t = ticker.trim().toUpperCase()
    if (!t) return

    run.mutate(
      { ticker: t, market: 'US', refresh: refresh || undefined },
      {
        onSuccess(data) {
          if (data.status === 'succeeded') {
            onNote(data as ResearchNote)
          } else {
            // queued or running
            onPending(data.note_id)
          }
        },
        onError(err) {
          if (
            err instanceof EntitlementError &&
            err.code === 'ENTITLEMENT_RESEARCH_AGENT_REQUIRES_PREMIUM'
          ) {
            onPremiumRequired()
          }
        },
      },
    )
  }

  const msg = errorMessage()

  return (
    <form onSubmit={handleSubmit} className="space-y-3" data-testid="run-form">
      <div className="flex gap-2">
        <input
          data-testid="ticker-input"
          type="text"
          aria-label="Ticker symbol"
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase().replace(/[^A-Z]/g, ''))}
          placeholder="TICKER"
          maxLength={10}
          className="w-36 rounded-lg border border-line bg-canvas px-3 py-2 font-mono text-sm uppercase tracking-wider text-txt placeholder:text-txtFaint focus:border-accent focus:outline-none"
        />
        <button
          data-testid="run-btn"
          type="submit"
          disabled={run.isPending || ticker.trim().length === 0}
          className="rounded-lg bg-accent/20 px-4 py-2 text-xs text-accent transition hover:bg-accent/30 disabled:opacity-40"
        >
          {run.isPending ? 'Starting…' : 'Generate note'}
        </button>
      </div>

      <label className="flex cursor-pointer items-center gap-2 text-[11px] text-txtDim">
        <input
          data-testid="refresh-checkbox"
          type="checkbox"
          checked={refresh}
          onChange={(e) => setRefresh(e.target.checked)}
          className="accent-accent"
        />
        Force refresh (bypass cache)
      </label>

      {msg && (
        <p
          className="rounded border border-neg/30 bg-neg/10 px-3 py-2 text-[11px] text-neg"
          data-testid="run-error"
        >
          {msg}
        </p>
      )}
    </form>
  )
}
