import type { IvSurface } from '../../lib/market'
import { UpgradeHint } from './UpgradeHint'

function atmIv(surface: IvSurface): { expiry: string; iv: number } | null {
  const e = surface.expiries[0]
  if (!e) return null
  // the surface gives per-strike iv_call/iv_put (nullable); need both for an ATM mid
  const usable = e.strikes.filter(
    (s): s is typeof s & { iv_call: number; iv_put: number } =>
      Number.isFinite(s.iv_call) && Number.isFinite(s.iv_put),
  )
  if (usable.length === 0) return null
  const s = usable.reduce((best, x) =>
    Math.abs(x.strike - surface.spot) < Math.abs(best.strike - surface.spot) ? x : best, usable[0])
  return { expiry: e.expiry, iv: ((s.iv_call + s.iv_put) / 2) * 100 }
}

export function MarketSnapshot({ symbol, surface, entitled, loading }: {
  symbol: string; surface: IvSurface | null; entitled: boolean; loading: boolean
}) {
  if (!entitled) {
    return (
      <div className="rounded-lg border border-line bg-panel p-4">
        <p className="mb-3 font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">Market snapshot</p>
        <UpgradeHint feature={`Live IV snapshot${symbol ? ` for ${symbol}` : ""}`} />
      </div>
    )
  }
  if (!symbol) {
    return (
      <div className="rounded-lg border border-line bg-panel p-4">
        <p className="mb-3 font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">Market snapshot</p>
        <p className="py-6 text-center text-sm text-txtFaint" data-testid="snapshot-empty">Hold a position to see its IV snapshot.</p>
      </div>
    )
  }
  const atm = surface ? atmIv(surface) : null
  return (
    <div className="rounded-lg border border-line bg-panel p-4" data-testid="snapshot">
      <p className="mb-3 font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">Market snapshot · {symbol}</p>
      {!surface ? (
        loading
          ? <div className="animate-pulse rounded bg-panel2 py-10" data-testid="snapshot-loading" />
          : <p className="py-6 text-center text-sm text-txtFaint">Snapshot unavailable.</p>
      ) : (
        <dl className="grid grid-cols-2 gap-3 font-mono text-xs text-txtDim">
          <div className="flex justify-between"><dt>spot</dt><dd className="tnum text-txt">{surface.spot.toFixed(2)}</dd></div>
          <div className="flex justify-between"><dt>ATM IV</dt><dd data-testid="snapshot-iv" className="tnum text-txt">{atm ? `${atm.iv.toFixed(1)}%` : "—"}</dd></div>
          <div className="flex justify-between"><dt>expiry</dt><dd className="text-txtDim">{atm?.expiry ?? "—"}</dd></div>
          <div className="flex justify-between"><dt>provider</dt><dd className="text-txtFaint">{surface.data_provider}</dd></div>
        </dl>
      )}
    </div>
  )
}
