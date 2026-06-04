import type { IvSurface, IvExpiry } from '../../lib/market'

const W = 360
const H = 180
const PAD = 30

function scaler(min: number, max: number, lo: number, hi: number) {
  const span = max - min || 1
  return (v: number) => lo + (hi - lo) * ((v - min) / span)
}

function atmIv(e: IvExpiry, spot: number): number {
  if (e.strikes.length === 0) return 0 // defensive: a malformed provider expiry can't sink the tab
  const s = e.strikes.reduce((best, x) =>
    Math.abs(x.strike - spot) < Math.abs(best.strike - spot) ? x : best, e.strikes[0])
  return ((s.calls.iv + s.puts.iv) / 2) * 100
}

function pointsAttr(pts: { x: number; y: number }[]): string {
  return pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
}

export function IvCurves({ surface, expiry }: { surface: IvSurface; expiry: string }) {
  const e = surface.expiries.find((x) => x.expiry === expiry) ?? surface.expiries[0]
  if (!e || e.strikes.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-txtFaint" data-testid="iv-empty">
        No surface data for this ticker.
      </p>
    )
  }

  const strikes = e ? e.strikes.map((s) => s.strike) : []
  const ivs = e ? e.strikes.flatMap((s) => [s.calls.iv * 100, s.puts.iv * 100]) : []
  const sx = scaler(Math.min(...strikes), Math.max(...strikes), PAD, W - PAD)
  const sy = scaler(Math.min(...ivs), Math.max(...ivs), H - PAD, PAD)
  const callPts = e ? e.strikes.map((s) => ({ x: sx(s.strike), y: sy(s.calls.iv * 100) })) : []
  const putPts = e ? e.strikes.map((s) => ({ x: sx(s.strike), y: sy(s.puts.iv * 100) })) : []

  const term = surface.expiries
    .filter((x) => x.strikes.length > 0)
    .map((x, i) => ({ i, iv: atmIv(x, surface.spot), expiry: x.expiry }))
  const tx = scaler(0, Math.max(1, term.length - 1), PAD, W - PAD)
  const tIvs = term.map((t) => t.iv)
  const ty = scaler(Math.min(...tIvs), Math.max(...tIvs), H - PAD, PAD)
  const termPts = term.map((t) => ({ x: tx(t.i), y: ty(t.iv) }))

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <figure className="rounded-lg border border-line bg-panel p-3">
        <figcaption className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">
          Smile · {expiry}
        </figcaption>
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" data-testid="iv-smile">
          <polyline data-testid="iv-smile-calls" points={pointsAttr(callPts)} fill="none" stroke="#37c98b" strokeWidth={1.8} />
          <polyline data-testid="iv-smile-puts" points={pointsAttr(putPts)} fill="none" stroke="#ff5d73" strokeWidth={1.8} strokeDasharray="4 3" />
        </svg>
      </figure>
      <figure className="rounded-lg border border-line bg-panel p-3">
        <figcaption className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">
          ATM term structure
        </figcaption>
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" data-testid="iv-term-structure">
          <polyline data-testid="iv-term-line" points={pointsAttr(termPts)} fill="none" stroke="#4da3ff" strokeWidth={1.8} />
          {termPts.map((p, i) => <circle key={i} cx={p.x} cy={p.y} r={2.5} fill="#4da3ff" />)}
        </svg>
      </figure>
    </div>
  )
}
