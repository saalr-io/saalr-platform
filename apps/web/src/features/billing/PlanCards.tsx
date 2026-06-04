import { TIERS, TIER_RANK, type TierName } from '../../lib/tiers'
import { useUpgrade } from './hooks'

export function PlanCards({ current, highlight }: { current: TierName; highlight?: TierName }) {
  const upgrade = useUpgrade()
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {TIERS.map((t) => {
        const isCurrent = t.key === current
        const isUpgrade = TIER_RANK[t.key] > TIER_RANK[current]
        const ring = (highlight ?? 'pro') === t.key && !isCurrent
        return (
          <div
            key={t.key}
            data-testid={`plan-${t.key}`}
            className={`relative flex flex-col rounded-lg border bg-panel p-5 ${
              ring ? 'border-accent' : 'border-line'
            }`}
          >
            <h3 className="font-mono text-sm uppercase tracking-[0.18em] text-txt">{t.name}</h3>
            <p className="mt-1 text-sm text-txtDim">{t.tagline}</p>
            <ul className="mt-4 space-y-2 text-sm text-txtDim">
              {t.features.map((f) => (
                <li key={f} className="flex gap-2">
                  <span aria-hidden className="font-mono text-pos">✓</span>
                  {f}
                </li>
              ))}
            </ul>
            <div className="mt-5">
              {isCurrent ? (
                <span
                  className="inline-block rounded-md border border-pos/30 px-4 py-2 text-xs text-pos"
                  data-testid={`plan-${t.key}-current`}
                >
                  Current plan
                </span>
              ) : isUpgrade ? (
                <button
                  onClick={() => upgrade.mutate(t.key as 'pro' | 'premium')}
                  disabled={upgrade.isPending}
                  className="rounded-md bg-accent px-4 py-2 text-xs font-medium text-canvas transition hover:opacity-90 disabled:opacity-50"
                >
                  {upgrade.isPending ? 'Starting…' : `Upgrade to ${t.name}`}
                </button>
              ) : null}
            </div>
            {upgrade.isError && isUpgrade && (
              <p className="mt-2 text-[11px] text-neg" data-testid={`plan-${t.key}-error`}>
                {upgrade.error?.message === 'FEATURE_UNAVAILABLE'
                  ? "Billing isn’t available right now."
                  : "Couldn’t start checkout — try again."}
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}
