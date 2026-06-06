import type { IvSurface, IvExpiry, IvStrike } from '../../lib/market'
import { InfoHint } from '../../components/InfoHint'
import { hintProps } from '../../content/helpHints'

// react-router path (resolved under the /app basename); see InfoHint for why not a plain href
const LESSON = '/education?lesson=volatility-surface'

const W = 360
const H = 180
const PAD = 30

function scaler(min: number, max: number, lo: number, hi: number) {
  const span = max - min || 1
  return (v: number) => lo + (hi - lo) * ((v - min) / span)
}

// A smile/term point needs BOTH a call and a put IV; the solve can leave either null
// on deep ITM/OTM strikes, and the bounded chain can include a strike with only one side.
function bothSides(s: IvStrike): s is IvStrike & { iv_call: number; iv_put: number } {
  return Number.isFinite(s.iv_call) && Number.isFinite(s.iv_put)
}

function atmIv(e: IvExpiry, spot: number): number | null {
  const usable = e.strikes.filter(bothSides)
  if (usable.length === 0) return null
  const s = usable.reduce((best, x) =>
    Math.abs(x.strike - spot) < Math.abs(best.strike - spot) ? x : best, usable[0])
  return ((s.iv_call + s.iv_put) / 2) * 100
}

function pointsAttr(pts: { x: number; y: number }[]): string {
  return pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
}

const fmtInt = (v: number) => String(Math.round(v))

// min / mid / max ticks by value, mapped to pixels through `scale`
function valueTicks(min: number, max: number, scale: (v: number) => number) {
  const vals = min === max ? [min] : [min, (min + max) / 2, max]
  return vals.map((v) => ({ pos: scale(v), label: fmtInt(v) }))
}

interface Tick { pos: number; label: string; emphasize?: boolean }

function AxisLayer({ xTicks, yTicks, xTitle }: { xTicks: Tick[]; yTicks: Tick[]; xTitle: string }) {
  const x0 = PAD
  const x1 = W - PAD
  const yBase = H - PAD
  return (
    <g fontFamily="monospace" fontSize={7}>
      <line x1={x0} y1={yBase} x2={x1} y2={yBase} stroke="#2c3340" strokeWidth={1} />
      <line x1={x0} y1={PAD} x2={x0} y2={yBase} stroke="#2c3340" strokeWidth={1} />
      {xTicks.map((t, i) => (
        <g key={`x${i}`}>
          <line x1={t.pos} y1={yBase} x2={t.pos} y2={yBase + 3} stroke="#2c3340" strokeWidth={1} />
          <text x={t.pos} y={yBase + 11} textAnchor="middle" fill={t.emphasize ? '#cbd5e1' : '#7b8494'}>{t.label}</text>
        </g>
      ))}
      {yTicks.map((t, i) => (
        <g key={`y${i}`}>
          <line x1={x0 - 3} y1={t.pos} x2={x0} y2={t.pos} stroke="#2c3340" strokeWidth={1} />
          <text x={x0 - 5} y={t.pos + 2.5} textAnchor="end" fill="#7b8494">{t.label}</text>
        </g>
      ))}
      <text x={(x0 + x1) / 2} y={H - 1} textAnchor="middle" fill="#5b6472">{xTitle}</text>
      <text x={2} y={PAD - 4} textAnchor="start" fill="#5b6472">IV %</text>
    </g>
  )
}

export function IvCurves({ surface, expiry }: { surface: IvSurface; expiry: string }) {
  const e = surface.expiries.find((x) => x.expiry === expiry) ?? surface.expiries[0]
  const usable = e ? e.strikes.filter(bothSides) : []
  if (!e || usable.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-txtFaint" data-testid="iv-empty">
        No surface data for this ticker.
      </p>
    )
  }

  const strikes = usable.map((s) => s.strike)
  const ivs = usable.flatMap((s) => [s.iv_call * 100, s.iv_put * 100])
  const sx = scaler(Math.min(...strikes), Math.max(...strikes), PAD, W - PAD)
  const sy = scaler(Math.min(...ivs), Math.max(...ivs), H - PAD, PAD)
  const callPts = usable.map((s) => ({ x: sx(s.strike), y: sy(s.iv_call * 100) }))
  const putPts = usable.map((s) => ({ x: sx(s.strike), y: sy(s.iv_put * 100) }))

  const term = surface.expiries
    .map((x) => ({ expiry: x.expiry, iv: atmIv(x, surface.spot) }))
    .filter((t): t is { expiry: string; iv: number } => t.iv !== null)
    .map((t, i) => ({ ...t, i }))
  const tx = scaler(0, Math.max(1, term.length - 1), PAD, W - PAD)
  const tIvs = term.map((t) => t.iv)
  const ty = scaler(Math.min(...tIvs), Math.max(...tIvs), H - PAD, PAD)
  const termPts = term.map((t) => ({ x: tx(t.i), y: ty(t.iv) }))

  // ── axes ──
  const strikeMin = Math.min(...strikes)
  const strikeMax = Math.max(...strikes)
  const atm = usable.reduce(
    (best, s) => (Math.abs(s.strike - surface.spot) < Math.abs(best - surface.spot) ? s.strike : best),
    strikes[0],
  )
  const smileXTicks: Tick[] = [
    { pos: sx(strikeMin), label: fmtInt(strikeMin) },
    ...(atm > strikeMin && atm < strikeMax ? [{ pos: sx(atm), label: fmtInt(atm), emphasize: true }] : []),
    { pos: sx(strikeMax), label: fmtInt(strikeMax) },
  ]
  const smileYTicks = valueTicks(Math.min(...ivs), Math.max(...ivs), sy)

  const termXIdx =
    term.length <= 1 ? [0] : term.length === 2 ? [0, 1] : [0, Math.floor((term.length - 1) / 2), term.length - 1]
  const termXTicks: Tick[] = termXIdx.map((i) => ({ pos: tx(i), label: term[i].expiry.slice(5) }))
  const termYTicks = valueTicks(Math.min(...tIvs), Math.max(...tIvs), ty)

  return (
    <div className="space-y-3">
      <div className="grid gap-4 lg:grid-cols-2">
        <figure className="rounded-lg border border-line bg-panel p-3">
          <figcaption className="mb-2 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">
            Smile · {expiry}
            <InfoHint {...hintProps('vol-surface')} />
          </figcaption>
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full" data-testid="iv-smile">
            <AxisLayer xTicks={smileXTicks} yTicks={smileYTicks} xTitle="strike" />
            <polyline data-testid="iv-smile-calls" points={pointsAttr(callPts)} fill="none" stroke="#37c98b" strokeWidth={1.8} />
            <polyline data-testid="iv-smile-puts" points={pointsAttr(putPts)} fill="none" stroke="#ff5d73" strokeWidth={1.8} strokeDasharray="4 3" />
          </svg>
        </figure>
        <figure className="rounded-lg border border-line bg-panel p-3">
          <figcaption className="mb-2 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">
            ATM term structure
            <InfoHint
              title="ATM term structure"
              body="This plots at-the-money IV across expiries. An upward slope means the market expects more movement later (or before an event); an inverted slope signals near-term stress."
              learnMoreTo={LESSON}
            />
          </figcaption>
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full" data-testid="iv-term-structure">
            <AxisLayer xTicks={termXTicks} yTicks={termYTicks} xTitle="expiry" />
            <polyline data-testid="iv-term-line" points={pointsAttr(termPts)} fill="none" stroke="#4da3ff" strokeWidth={1.8} />
            {termPts.map((p, i) => <circle key={i} cx={p.x} cy={p.y} r={2.5} fill="#4da3ff" />)}
          </svg>
        </figure>
      </div>
      <p className="flex items-center gap-1.5 font-mono text-[10px] text-txtFaint">
        Model-priced IV · approximate
        <InfoHint
          title="Model-priced IV"
          body="Saalr derives IV from a Black-Scholes fit to option mid-prices, not vendor greeks. It is directionally accurate and great for reading shape, but a single number is not an exact dealer quote."
          learnMoreTo={LESSON}
        />
      </p>
    </div>
  )
}
