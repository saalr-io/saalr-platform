import { useHealth } from '../hooks/useHealth'
import { StatusDot, type HealthState } from './StatusDot'
import { Clock } from './Clock'

export function Topbar() {
  const q = useHealth()
  const state: HealthState = q.isError ? 'error' : q.isSuccess ? 'ok' : 'loading'
  const label =
    state === 'ok'
      ? `API live · ${q.data?.latencyMs ?? 0}ms`
      : state === 'error'
        ? 'API unreachable'
        : 'API · checking'

  return (
    <header className="col-span-2 flex items-center gap-4 border-b border-line bg-canvas/70 px-5 backdrop-blur-md">
      <div className="flex items-center gap-2.5">
        <span className="grid h-7 w-7 place-items-center rounded-lg bg-gradient-to-br from-pos to-accent text-sm font-extrabold text-[#04110d] shadow-[0_0_18px_-2px] shadow-pos">
          S
        </span>
        <span className="font-semibold tracking-tight">Saalr</span>
        <span className="font-mono text-[9px] tracking-[2.5px] text-txtFaint">RESEARCH&nbsp;TERMINAL</span>
      </div>

      <div className="flex items-center gap-2 rounded-lg border border-line bg-panel px-2.5 py-1 text-xs">
        <span className="h-1.5 w-1.5 rounded-full bg-pos shadow-[0_0_8px] shadow-pos" />
        Acme Capital
        <span className="rounded-full border border-[#34406b] bg-accent2/20 px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider text-[#cdbcff]">
          Premium
        </span>
      </div>

      <label className="hidden items-center gap-2 rounded-lg border border-line bg-panel px-3 py-1.5 text-txtFaint lg:flex">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.2-3.2" strokeLinecap="round" />
        </svg>
        <span className="text-xs">Search ticker, strategy</span>
        <kbd className="ml-3 rounded border border-line bg-panel2 px-1.5 py-0.5 font-mono text-[9px]">/</kbd>
      </label>

      <div className="flex-1" />
      <Clock />
      <span className="h-4 w-px bg-line" />
      <StatusDot state={state} label={label} />
    </header>
  )
}
