import type { PriceForecast, PriceModel } from '../../lib/models'
import { InfoHint } from '../../components/InfoHint'
import { hintProps } from '../../content/helpHints'

const W = 380
const H = 200
const PAD = { l: 40, r: 12, t: 14, b: 28 }

const COLOR: Record<PriceModel['model'], string> = {
  arima: '#4da3ff',
  lstm: '#c084fc',
  naive: '#9aa4b2',
}

export function PriceForecastPanel({ forecast }: { forecast: PriceForecast }) {
  const { models, last_close, horizon_days, primary_model } = forecast
  const n = horizon_days
  const allY = [
    last_close,
    ...models.flatMap((m) => m.path),
    ...models.flatMap((m) => (m.ci_95 ? m.ci_95.flat() : [])),
  ]
  const yMin = Math.min(...allY)
  const yMax = Math.max(...allY)
  const ySpan = yMax - yMin || 1
  const sx = (i: number) => PAD.l + (W - PAD.l - PAD.r) * (i / Math.max(1, n))
  const sy = (v: number) => H - PAD.b - (H - PAD.t - PAD.b) * ((v - yMin) / ySpan)

  const primary = models.find((m) => m.model === primary_model)
  const yTicks = [yMin, (yMin + yMax) / 2, yMax]

  return (
    <figure className="rounded-lg border border-line bg-panel p-4" data-testid="price-forecast-panel">
      <figcaption className="mb-2 flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">
        Price forecast · {horizon_days}d
        <InfoHint {...hintProps('price-forecast')} />
        <span data-testid="pf-primary" className="rounded bg-accent/20 px-1.5 py-0.5 text-accent">{primary_model} wins backtest</span>
        {forecast.approximate && <span className="rounded border border-line px-1.5 py-0.5 text-txtFaint">approximate</span>}
      </figcaption>

      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        <g fontFamily="monospace" fontSize={8.5}>
          <line data-testid="pf-axis-y" x1={PAD.l} y1={PAD.t} x2={PAD.l} y2={H - PAD.b} stroke="#2c3340" />
          <line data-testid="pf-axis-x" x1={PAD.l} y1={H - PAD.b} x2={W - PAD.r} y2={H - PAD.b} stroke="#2c3340" />
          {yTicks.map((v, i) => (
            <g key={i}>
              <line x1={PAD.l - 3} y1={sy(v)} x2={PAD.l} y2={sy(v)} stroke="#2c3340" />
              <text x={PAD.l - 5} y={sy(v) + 3} textAnchor="end" fill="#5b6472">{v.toFixed(0)}</text>
            </g>
          ))}
          <text x={PAD.l} y={H - 1} textAnchor="start" fill="#5b6472">today</text>
          <text x={W - PAD.r} y={H - 1} textAnchor="end" fill="#5b6472">+{n}d</text>
          <text x={4} y={PAD.t - 4} textAnchor="start" fill="#5b6472">price</text>
        </g>

        {primary?.ci_95 && (
          <polygon
            data-testid="pf-band"
            points={[
              `${sx(0).toFixed(1)},${sy(last_close).toFixed(1)}`,
              ...primary.ci_95.map((p, i) => `${sx(i + 1).toFixed(1)},${sy(p[1]).toFixed(1)}`),
              ...primary.ci_95.map((p, i) => `${sx(i + 1).toFixed(1)},${sy(p[0]).toFixed(1)}`).reverse(),
            ].join(' ')}
            fill="#4da3ff18"
            stroke="none"
          />
        )}

        {models.map((m) => (
          <polyline
            key={m.model}
            data-testid="pf-line"
            points={[`${sx(0).toFixed(1)},${sy(last_close).toFixed(1)}`,
              ...m.path.map((v, i) => `${sx(i + 1).toFixed(1)},${sy(v).toFixed(1)}`)].join(' ')}
            fill="none"
            stroke={COLOR[m.model]}
            strokeWidth={m.model === primary_model ? 2.2 : 1.3}
            strokeDasharray={m.model === 'naive' ? '3 3' : undefined}
          />
        ))}
      </svg>

      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10px]">
        {models.map((m) => (
          <span key={m.model} className="flex items-center gap-1" style={{ color: COLOR[m.model] }}>
            <span style={{ background: COLOR[m.model] }} className="inline-block h-2 w-2 rounded-sm" />
            {m.model} {m.expected_return_pct >= 0 ? '+' : ''}{m.expected_return_pct.toFixed(1)}%
          </span>
        ))}
      </div>

      <p className="mt-2 text-[11px] text-txtFaint" data-testid="pf-disclaimer">{forecast.disclaimer}</p>

      <dl className="mt-2 grid grid-cols-3 gap-x-4 gap-y-1 font-mono text-[10px] text-txtDim">
        {models.map((m) => (
          <div key={m.model} className="flex justify-between">
            <dt>{m.model} MAE</dt>
            <dd className="tnum">{m.holdout_mae.toFixed(2)} · {(m.directional_accuracy * 100).toFixed(0)}%</dd>
          </div>
        ))}
      </dl>
    </figure>
  )
}
