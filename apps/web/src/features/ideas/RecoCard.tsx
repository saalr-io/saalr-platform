import type React from 'react'
import type { Recommendation } from '../../lib/regime'

function Badge({ children, tone }: { children: React.ReactNode; tone?: 'warn' }) {
  return (
    <span
      className={`rounded px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wide ${
        tone === 'warn' ? 'bg-warn/15 text-warn' : 'border border-lineSoft text-txtFaint'
      }`}
    >
      {children}
    </span>
  )
}

export function RecoCard({
  reco, onApply, applying,
}: {
  reco: Recommendation; onApply: (key: string) => void; applying: boolean
}) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-line bg-panel p-3" data-testid={`reco-${reco.template_key}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[13px] font-medium text-txt">{reco.name}</span>
        <span className="tnum font-mono text-[10px] text-txtFaint">score {reco.score}</span>
      </div>
      <p className="text-[11px] leading-snug text-txtDim">{reco.rationale}</p>
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge>{reco.net}</Badge>
        <Badge tone={reco.risk === 'undefined' ? 'warn' : undefined}>
          {reco.risk === 'undefined' ? 'undefined risk' : 'defined risk'}
        </Badge>
        <button
          data-testid={`reco-apply-${reco.template_key}`}
          onClick={() => onApply(reco.template_key)}
          disabled={applying}
          className="ml-auto rounded-md bg-accent px-3 py-1 text-[11px] font-medium text-canvas transition hover:opacity-90 disabled:opacity-40"
        >
          {applying ? "Opening…" : "Apply"}
        </button>
      </div>
    </div>
  )
}
