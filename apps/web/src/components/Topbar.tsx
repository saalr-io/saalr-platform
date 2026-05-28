import { useHealth } from '../hooks/useHealth'
import { StatusDot, type HealthState } from './StatusDot'

export function Topbar() {
  const q = useHealth()
  const state: HealthState = q.isError ? 'error' : q.isSuccess ? 'ok' : 'loading'
  const label =
    state === 'ok'
      ? `API live Â· ${q.data?.latencyMs ?? 0}ms`
      : state === 'error'
        ? 'API unreachable'
        : 'API â€¦'

  return (
    <header className="col-span-2 flex items-center gap-4 border-b border-line bg-canvas/70 px-5 backdrop-blur">
      <div className="flex items-center gap-2 font-bold tracking-wide">
        <span className="grid h-6 w-6 place-items-center rounded-md bg-gradient-to-br from-pos to-accent font-extrabold text-[#04110d]">
          S
        </span>
        Saalr <span className="text-[9px] tracking-[2px] text-txtFaint">RESEARCH TERMINAL</span>
      </div>
      <div className="flex items-center gap-2 rounded-lg border border-line bg-panel px-2.5 py-1 text-xs">
        <span className="h-2 w-2 rounded-full bg-pos shadow-[0_0_8px] shadow-pos" /> Acme Capital
        <span className="rounded-full border border-[#34406b] bg-accent2/20 px-2 py-0.5 text-[9px] uppercase tracking-wider text-[#cdbcff]">
          Premium
        </span>
      </div>
      <div className="flex-1" />
      <StatusDot state={state} label={label} />
    </header>
  )
}