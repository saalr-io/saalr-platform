import type { Regime } from '../../lib/regime'

const PRETTY: Record<string, string> = {
  strong_bullish: 'Strong bullish', bullish: 'Bullish', neutral: 'Neutral',
  bearish: 'Bearish', strong_bearish: 'Strong bearish',
  low: 'Low', normal: 'Normal', high: 'High',
  trending: 'Trending', range_bound: 'Range-bound',
  rising: 'Rising', falling: 'Falling', stable: 'Stable',
}
const pretty = (s: string) => PRETTY[s] ?? s

function Cell({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="rounded-lg border border-line bg-panel p-3">
      <p className="font-mono text-[9px] uppercase tracking-wider text-txtFaint">{label}</p>
      <p className="mt-1 text-sm font-semibold text-txt">{value}</p>
      <p className="mt-1 text-[11px] leading-snug text-txtDim">{detail}</p>
    </div>
  )
}

export function RegimePanel({ regime }: { regime: Regime }) {
  return (
    <div className="space-y-3" data-testid="regime-panel">
      <p className="text-lg font-semibold tracking-tight" data-testid="regime-headline">{regime.headline}</p>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <Cell label="Direction" value={pretty(regime.direction.label)} detail={regime.direction.detail} />
        <Cell label="Volatility" value={pretty(regime.volatility.label)} detail={regime.volatility.detail} />
        <Cell label="Momentum" value={pretty(regime.momentum.label)} detail={regime.momentum.detail} />
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {regime.premium_available && regime.premium ? (
          <>
            <Cell label="Vol trend · premium" value={pretty(regime.premium.vol_trend.label)} detail={regime.premium.vol_trend.detail} />
            <Cell label="Sentiment · premium" value={pretty(regime.premium.sentiment.label)} detail={regime.premium.sentiment.detail} />
          </>
        ) : (
          <a
            href="/app/billing"
            data-testid="regime-upgrade"
            className="rounded-lg border border-dashed border-line bg-panel2 p-3 text-[11px] text-txtDim transition-colors hover:text-txt sm:col-span-2"
          >
            Unlock GARCH vol-trend + news sentiment with a Pro or Premium plan →
          </a>
        )}
      </div>
    </div>
  )
}
