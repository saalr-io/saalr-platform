import { useSearchParams } from 'react-router-dom'
import { PlanCards } from '../features/billing/PlanCards'
import { useSubscription, usePortal } from '../features/billing/hooks'
import type { TierName } from '../lib/tiers'

function fmtDate(iso: string | null): string {
  return iso ? new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : ''
}

export function Billing() {
  const { data, isLoading } = useSubscription()
  const portal = usePortal()
  const [params] = useSearchParams()
  const highlight = (params.get('plan') as TierName | null) ?? undefined
  const current = (data?.tier ?? 'free') as TierName

  return (
    <div className="animate-fadeUp space-y-6">
      <div>
        <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">// Billing</p>
        <h2 className="mt-1 text-xl font-semibold tracking-tight">Plans &amp; billing</h2>
        {!isLoading && data && (
          <p className="mt-2 text-sm text-txtDim" data-testid="current-plan">
            Current plan: <span className="text-txt">{current}</span>
            {data.status !== 'active' ? ` (${data.status})` : ''}
            {data.current_period_end
              ? data.cancel_at_period_end
                ? ` · cancels ${fmtDate(data.current_period_end)}`
                : current !== 'free'
                  ? ` · renews ${fmtDate(data.current_period_end)}`
                  : ''
              : ''}
          </p>
        )}
      </div>

      <PlanCards current={current} highlight={highlight} />

      {data?.has_customer && (
        <div>
          <button
            data-testid="manage-billing"
            onClick={() => portal.mutate()}
            disabled={portal.isPending}
            className="rounded-md border border-line px-4 py-2 text-xs text-txtDim transition hover:border-accent hover:text-txt disabled:opacity-50"
          >
            {portal.isPending ? "Opening…" : "Manage billing"}
          </button>
          {portal.isError && (
            <span className="ml-3 text-[11px] text-neg" data-testid="manage-error">
              Couldn&rsquo;t open the billing portal — try again.
            </span>
          )}
        </div>
      )}
    </div>
  )
}
