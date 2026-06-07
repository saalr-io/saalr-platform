// ── PremiumGate ────────────────────────────────────────────────────────────
// Shown when any research call returns ENTITLEMENT_RESEARCH_AGENT_REQUIRES_PREMIUM.

import { Link } from 'react-router-dom'

export function PremiumGate() {
  return (
    <div
      className="rounded-xl border border-accent/30 bg-accent/5 px-6 py-12 text-center"
      data-testid="premium-gate"
    >
      <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">
        // Premium feature
      </p>
      <h3 className="mt-3 text-lg font-semibold tracking-tight text-txt">
        Research notes are a Premium feature
      </h3>
      <p className="mt-2 text-sm text-txtDim">
        Upgrade to Premium to run the 6-agent research desk — fundamentals, sentiment,
        technical, risk, trader, and PM — and receive a structured note with signals and
        sources for any US ticker.
      </p>
      <Link
        to="/billing?plan=premium"
        className="mt-5 inline-block rounded-md bg-accent px-5 py-2.5 text-sm font-medium text-canvas transition hover:opacity-90"
      >
        Upgrade to Premium
      </Link>
    </div>
  )
}
