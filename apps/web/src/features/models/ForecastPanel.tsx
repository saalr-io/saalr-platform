import type { VolForecast } from '../../lib/models'
import { InfoHint } from '../../components/InfoHint'
import { hintProps } from '../../content/helpHints'

const W = 360
const H = 180
const PAD = 30

function scaler(min: number, max: number, lo: number, hi: number) {
  const span = max - min || 1
  return (v: number) => lo + (hi - lo) * ((v - min) / span)
}

export function ForecastPanel({ forecast }: { forecast: VolForecast }) {
  const fc = forecast.primary_forecast
  const ci = forecast.primary_ci_95
  const n = fc.length
  const xs = scaler(0, Math.max(1, n - 1), PAD, W - PAD)
  const allYs = [...fc, ...(ci ? ci.flat() : [])]
  const ys = scaler(Math.min(...allYs), Math.max(...allYs), H - PAD, PAD)

  const linePts = fc.map((v, i) => `${xs(i).toFixed(1)},${ys(v).toFixed(1)}`).join(' ')
  const band = ci
    ? [
        ...ci.map((p, i) => `${xs(i).toFixed(1)},${ys(p[1]).toFixed(1)}`),
        ...ci.map((p, i) => `${xs(i).toFixed(1)},${ys(p[0]).toFixed(1)}`).reverse(),
      ].join(' ')
    : null

  return (
    <figure className="rounded-lg border border-line bg-panel p-4" data-testid="forecast-panel">
      <figcaption className="mb-2 flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">
        Vol forecast · {forecast.horizon_days}d
        <InfoHint {...hintProps('vol-forecast')} />
        <span data-testid="forecast-primary" className="rounded bg-accent/20 px-1.5 py-0.5 text-accent">{forecast.primary_model}</span>
        {forecast.approximate && <span className="rounded border border-line px-1.5 py-0.5 text-txtFaint">approximate</span>}
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        {band && <polygon data-testid="forecast-ci" points={band} fill="#4da3ff22" stroke="none" />}
        <polyline data-testid="forecast-line" points={linePts} fill="none" stroke="#4da3ff" strokeWidth={1.8} />
        {n === 1 && <circle cx={xs(0)} cy={ys(fc[0])} r={3} fill="#4da3ff" />}
      </svg>
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-[11px] text-txtDim">
        <div className="flex justify-between"><dt>lift</dt><dd className="tnum text-txt">{forecast.validation.lift.toFixed(3)}</dd></div>
        <div className="flex justify-between"><dt>garch MAE</dt><dd className="tnum">{forecast.validation.garch_mae.toFixed(3)}</dd></div>
        <div className="flex justify-between"><dt>hv21 MAE</dt><dd className="tnum">{forecast.validation.hv21_mae.toFixed(3)}</dd></div>
        <div className="flex justify-between"><dt>har MAE</dt><dd className="tnum">{forecast.validation.har_mae.toFixed(3)}</dd></div>
        <div className="flex justify-between"><dt>ω/α/β</dt><dd className="tnum">{forecast.params.omega.toFixed(4)}/{forecast.params.alpha.toFixed(2)}/{forecast.params.beta.toFixed(2)}</dd></div>
      </dl>
      {forecast.alternative_models.map((a) => (
        <p key={a.model} className="mt-2 text-[11px] text-txtFaint" data-testid="forecast-alt">
          alt: {a.model} ({a.status.replace(/_/g, " ")})
        </p>
      ))}
    </figure>
  )
}
