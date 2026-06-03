import { EntitlementError } from '../../lib/content'
import { useModule, useComplete } from './hooks'
import { Markdown } from './markdown'

// ── upgrade nudge ──────────────────────────────────────────────────────────

function UpgradeNudge({ label }: { label: string }) {
  return (
    <div
      className="rounded-lg border border-accent/30 bg-accent/5 px-4 py-6 text-center"
      data-testid="upgrade-nudge"
    >
      <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-accent">
        // Upgrade required
      </p>
      <p className="mt-2 text-sm text-txtDim">{label}</p>
      <p className="mt-3 text-[11px] text-txtFaint">
        Upgrade to Pro to unlock this lesson and the full academy catalog.
      </p>
    </div>
  )
}

// ── component ──────────────────────────────────────────────────────────────

interface ModuleReaderProps {
  slug: string
}

export function ModuleReader({ slug }: ModuleReaderProps) {
  const { data, isLoading, error } = useModule(slug)
  const complete = useComplete()

  if (isLoading) {
    return (
      <div className="animate-pulse space-y-3 p-4">
        <div className="h-5 w-1/2 rounded bg-panel2" />
        <div className="h-3 w-3/4 rounded bg-panel2" />
        <div className="h-3 w-2/3 rounded bg-panel2" />
      </div>
    )
  }

  if (error) {
    if (error instanceof EntitlementError) {
      return <UpgradeNudge label="This lesson needs Pro" />
    }
    return (
      <div
        className="rounded-lg border border-neg/30 bg-neg/10 px-4 py-3 text-xs text-neg"
        data-testid="reader-error"
      >
        Failed to load lesson: {error.message}
      </div>
    )
  }

  if (!data) return null

  const isDone = data.status === 'completed'

  return (
    <div className="animate-fadeUp space-y-5 p-1">
      {/* header */}
      <div>
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-txtFaint">
            // Lesson {String(data.order).padStart(2, '0')}
          </span>
          <span className="font-mono text-[10px] text-txtFaint">{data.est_minutes} min</span>
        </div>
        <h2 className="mt-1 text-xl font-semibold tracking-tight text-txt">{data.title}</h2>
        <p className="mt-1 text-sm text-txtDim">{data.summary}</p>
      </div>

      <div className="h-px bg-line" />

      {/* body */}
      <Markdown source={data.body} />

      <div className="h-px bg-line" />

      {/* complete button */}
      <div className="flex items-center gap-3">
        <button
          data-testid="complete-btn"
          disabled={isDone || complete.isPending}
          onClick={() => complete.mutate(slug)}
          className={`rounded px-4 py-1.5 text-xs transition-colors ${
            isDone
              ? 'cursor-default border border-pos/30 text-pos'
              : 'bg-pos/20 text-pos hover:bg-pos/30'
          }`}
        >
          {isDone ? '✓ Completed' : complete.isPending ? 'Saving…' : 'Mark complete'}
        </button>
        {complete.isError && (
          <span className="text-[11px] text-neg" data-testid="complete-error">
            {complete.error instanceof EntitlementError
              ? 'Pro required to mark complete.'
              : 'Failed — please try again.'}
          </span>
        )}
      </div>
    </div>
  )
}
