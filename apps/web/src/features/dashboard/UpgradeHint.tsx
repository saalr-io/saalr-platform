import { Link } from 'react-router-dom'

export function UpgradeHint({ feature, plan = 'pro' }: { feature: string; plan?: 'pro' | 'premium' }) {
  return (
    <div className="rounded-lg border border-accent/30 bg-accent/5 p-4 text-center" data-testid="upgrade-hint">
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-accent">// Pro</p>
      <p className="mt-2 text-sm text-txtDim">{feature}</p>
      <Link to={`/billing?plan=${plan}`} className="mt-3 inline-block rounded-md bg-accent px-4 py-1.5 text-xs font-medium text-canvas transition hover:opacity-90">
        Upgrade
      </Link>
    </div>
  )
}
