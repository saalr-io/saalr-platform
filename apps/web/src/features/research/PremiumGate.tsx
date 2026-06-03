// ── PremiumGate ────────────────────────────────────────────────────────────
// Shown when any research call returns ENTITLEMENT_RESEARCH_AGENT_REQUIRES_PREMIUM.

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
      <p className="mt-4 text-[11px] text-txtFaint">
        Contact your account team or visit the upgrade page to unlock Research Agent.
      </p>
    </div>
  )
}
