import { Link } from 'react-router-dom'

export function ModelsGate() {
  return (
    <div className="rounded-xl border border-accent/30 bg-accent/5 px-6 py-12 text-center" data-testid="models-gate">
      <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">// Pro feature</p>
      <h3 className="mt-3 text-lg font-semibold tracking-tight text-txt">
        Forecasts &amp; Monte-Carlo are a Pro feature
      </h3>
      <p className="mt-2 text-sm text-txtDim">
        Upgrade to Pro for GARCH volatility forecasts with walk-forward validation, news
        sentiment, and Monte-Carlo probability-of-profit on any strategy.
      </p>
      <Link
        to="/billing?plan=pro"
        className="mt-5 inline-block rounded-md bg-accent px-5 py-2.5 text-sm font-medium text-canvas transition hover:opacity-90"
      >
        Upgrade to Pro
      </Link>
    </div>
  )
}
