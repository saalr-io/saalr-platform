import type { Sentiment } from '../../lib/models'

const W = 240
const H = 28

const LABEL_CLS: Record<string, string> = { bearish: 'text-neg', neutral: 'text-warn', bullish: 'text-pos' }

export function SentimentGauge({ sentiment }: { sentiment: Sentiment }) {
  if (!sentiment.has_data) {
    return (
      <div className="rounded-lg border border-line bg-panel p-4" data-testid="sentiment-empty">
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">News sentiment</p>
        <p className="mt-3 text-sm text-txtFaint">No sentiment coverage yet for {sentiment.ticker}.</p>
      </div>
    )
  }
  const cx = ((sentiment.score + 1) / 2) * W
  return (
    <div className="rounded-lg border border-line bg-panel p-4" data-testid="sentiment-panel">
      <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-txtDim">News sentiment</p>
      <div className="mt-3 flex items-baseline gap-2">
        <span data-testid="sentiment-label" className={`text-lg font-semibold ${LABEL_CLS[sentiment.label] ?? 'text-txt'}`}>
          {sentiment.label}
        </span>
        <span className="tnum font-mono text-sm text-txtDim">{sentiment.score.toFixed(2)}</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-3 w-full" data-testid="sentiment-gauge">
        <line x1={0} y1={H / 2} x2={W} y2={H / 2} stroke="#2a2f3a" strokeWidth={3} strokeLinecap="round" />
        <line x1={W / 2} y1={4} x2={W / 2} y2={H - 4} stroke="#3a4150" strokeWidth={1} />
        <circle data-testid="sentiment-marker" cx={cx} cy={H / 2} r={5} fill="#e6e9ef" />
      </svg>
      <p className="mt-3 font-mono text-[11px] text-txtFaint">
        {sentiment.confident ? "confident" : "low confidence"} · {sentiment.n_headlines} headlines
        {sentiment.as_of ? ` · ${new Date(sentiment.as_of).toLocaleDateString()}` : ""}
      </p>
    </div>
  )
}
