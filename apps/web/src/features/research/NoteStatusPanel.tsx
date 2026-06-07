// ── NoteStatusPanel ────────────────────────────────────────────────────────
// Shown while a note is queued/running, or when it has failed.

interface Props {
  ticker: string
  status: 'queued' | 'running' | 'failed'
  errorMessage?: string
}

export function NoteStatusPanel({ ticker, status, errorMessage }: Props) {
  if (status === 'failed') {
    return (
      <div
        className="rounded-lg border border-neg/30 bg-neg/10 px-4 py-4"
        data-testid="note-failed"
      >
        <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-neg">
          // Research failed
        </p>
        <p className="mt-1 text-sm text-neg">
          {errorMessage ?? 'The research run failed. Please try again.'}
        </p>
      </div>
    )
  }

  return (
    <div
      className="rounded-lg border border-line bg-panel px-4 py-6 text-center"
      data-testid="note-running"
    >
      <p className="animate-pulse font-mono text-[11px] uppercase tracking-[0.18em] text-accent">
        // Researching {ticker}…
      </p>
      <p className="mt-2 text-sm text-txtDim">
        Running the 6-agent desk (fundamentals · sentiment · technical · risk · trader · PM)
      </p>
      <p className="mt-3 font-mono text-[10px] text-txtFaint">
        {status === 'queued' ? 'Queued — starting shortly…' : 'In progress — this may take up to a minute.'}
      </p>
    </div>
  )
}
