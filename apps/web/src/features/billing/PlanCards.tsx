import { useState } from 'react'
import { TIERS, TIER_RANK, type TierName } from '../../lib/tiers'
import { useUpgrade } from './hooks'
import type { Interval } from '../../lib/billing'

export function PlanCards({ current, highlight }: { current: TierName; highlight?: TierName }) {
  const upgrade = useUpgrade()
  const [interval, setInterval] = useState<Interval>('monthly')
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-1 text-xs" role="group" aria-label="Billing interval">
        {(['monthly', 'annual'] as Interval[]).map((iv) => (
          <button key={iv} data-testid={`billing-interval-${iv}`} onClick={() => setInterval(iv)}
            className={`rounded-full px-3 py-1 ${interval === iv ? 'bg-accent text-canvas' : 'text-txtDim hover:text-txt'}`}>
            {iv === 'monthly' ? 'Monthly' : 'Annual'}
          </button>
        ))}
        {interval === 'annual' && <span className="ml-2 text-[11px] text-pos">2 months free</span>}
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        {TIERS.map((t) => {
          const isCurrent = t.key === current
          const isUpgrade = TIER_RANK[t.key] > TIER_RANK[current]
          const ring = (highlight ?? 'pro') === t.key && !isCurrent
          return (
            <div key={t.key} data-testid={`plan-${t.key}`}
              className={`relative flex flex-col rounded-lg border bg-panel p-5 ${ring ? 'border-accent' : 'border-line'}`}>
              <h3 className="font-mono text-sm uppercase tracking-[0.18em] text-txt">{t.name}</h3>
              <p className="mt-1 text-sm text-txtDim">{t.tagline}</p>
              {interval === 'annual' && t.key !== 'free' && (
                <span data-testid="annual-badge" className="mt-2 inline-block w-fit rounded bg-pos/15 px-2 py-0.5 text-[11px] text-pos">
                  Save 17% · 2 months free
                </span>
              )}
              <ul className="mt-4 space-y-2 text-sm text-txtDim">
                {t.features.map((f) => (
                  <li key={f} className="flex gap-2"><span aria-hidden className="font-mono text-pos">✓</span>{f}</li>
                ))}
              </ul>
              <div className="mt-5">
                {isCurrent ? (
                  <span className="inline-block rounded-md border border-pos/30 px-4 py-2 text-xs text-pos" data-testid={`plan-${t.key}-current`}>Current plan</span>
                ) : isUpgrade ? (
                  <button onClick={() => upgrade.mutate({ tier: t.key as 'pro' | 'premium', interval })}
                    disabled={upgrade.isPending}
                    className="rounded-md bg-accent px-4 py-2 text-xs font-medium text-canvas transition hover:opacity-90 disabled:opacity-50">
                    {upgrade.isPending ? 'Starting…' : `Upgrade to ${t.name}`}
                  </button>
                ) : null}
              </div>
              {upgrade.isError && isUpgrade && (
                <p className="mt-2 text-[11px] text-neg" data-testid={`plan-${t.key}-error`}>
                  {upgrade.error?.message === 'FEATURE_UNAVAILABLE' ? "Billing isn't available right now." : "Couldn't start checkout — try again."}
                </p>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
