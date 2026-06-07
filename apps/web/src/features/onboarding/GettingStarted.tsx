import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useOnboarding } from './hooks'
import { ONBOARDING_STEPS } from '../../lib/onboarding'

const META: Record<string, { label: string; to: string }> = {
  build_strategy: { label: 'Build your first strategy', to: '/strategies' },
  see_regime: { label: "See a ticker's market regime", to: '/ideas' },
  paper_trade: { label: 'Paper-trade a strategy', to: '/start' },
  read_lesson: { label: 'Read an OptionsAcademy lesson', to: '/education' },
}
const KEY = 'saalr.onboarding.dismissed'

export function GettingStarted() {
  const [dismissed, setDismissed] = useState(() => localStorage.getItem(KEY) === '1')
  const { data } = useOnboarding(!dismissed)
  if (dismissed || !data || data.all_done) return null
  const done = new Set(data.steps)
  return (
    <div className="rounded-lg border border-accent/40 bg-accent/5 p-4" data-testid="getting-started">
      <div className="mb-2 flex items-center justify-between">
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent">
          Getting started · {data.steps.filter((s) => s in META).length}/{ONBOARDING_STEPS.length}
        </p>
        <button type="button" data-testid="ob-dismiss" onClick={() => { localStorage.setItem(KEY, '1'); setDismissed(true) }}
          className="text-[11px] text-txtFaint hover:text-txt">Dismiss</button>
      </div>
      <ul className="space-y-1.5">
        {ONBOARDING_STEPS.map((s) => (
          <li key={s} data-testid={`ob-step-${s}`} className="flex items-center gap-2 text-sm">
            <span className={done.has(s) ? 'text-pos' : 'text-txtFaint'}>{done.has(s) ? '✓' : '○'}</span>
            {done.has(s)
              ? <span className="text-txtDim line-through">{META[s].label}</span>
              : <Link to={META[s].to} className="text-txt hover:text-accent">{META[s].label} →</Link>}
          </li>
        ))}
      </ul>
    </div>
  )
}
