import type React from 'react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
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

export type PaperState = 'idle' | 'pending' | { placed: number; rejected: number }

export function RecoCard({
  reco, onApply, applying, onPaperTrade, paperState,
}: {
  reco: Recommendation
  onApply: (key: string) => void
  applying: boolean
  onPaperTrade: (key: string) => void
  paperState: PaperState
}) {
  const [confirming, setConfirming] = useState(false)
  const k = reco.template_key
  const done = typeof paperState === 'object' ? paperState : null

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-line bg-panel p-3" data-testid={`reco-${k}`}>
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
          type="button"
          data-testid={`reco-paper-${k}`}
          onClick={() => setConfirming(true)}
          disabled={paperState === 'pending'}
          className="ml-auto rounded-md border border-line px-3 py-1 text-[11px] text-txtDim transition-colors hover:text-txt disabled:opacity-40"
        >
          {paperState === 'pending' ? "Placing…" : "Paper trade"}
        </button>
        <button
          type="button"
          data-testid={`reco-apply-${k}`}
          onClick={() => onApply(k)}
          disabled={applying}
          className="rounded-md bg-accent px-3 py-1 text-[11px] font-medium text-canvas transition hover:opacity-90 disabled:opacity-40"
        >
          {applying ? "Opening…" : "Apply"}
        </button>
      </div>

      {confirming && !done && (
        <div className="rounded-md border border-dashed border-line bg-panel2 p-2.5 text-[11px] text-txtDim" data-testid={`reco-confirm-${k}`}>
          Places risk-free paper orders for <span className="text-txt">{reco.name}</span> into your Practice
          account so you can watch how the trade behaves.
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              data-testid={`reco-confirm-place-${k}`}
              onClick={() => { setConfirming(false); onPaperTrade(k) }}
              className="rounded bg-accent px-3 py-1 text-[11px] font-medium text-canvas hover:opacity-90"
            >
              Place paper trade
            </button>
            <button type="button" onClick={() => setConfirming(false)} className="px-2 py-1 text-[11px] text-txtFaint hover:text-txt">
              Cancel
            </button>
          </div>
        </div>
      )}

      {done && (
        <p className="text-[11px] text-txtDim" data-testid={`reco-paper-done-${k}`}>
          Placed {done.placed} paper order{done.placed === 1 ? '' : 's'}
          {done.rejected > 0 ? ` · ${done.rejected} couldn't fill (need market data)` : ''} ·{' '}
          <Link to="/portfolio" className="text-accent hover:underline">View in Portfolio →</Link>
        </p>
      )}
    </div>
  )
}
