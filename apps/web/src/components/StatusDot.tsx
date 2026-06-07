export type HealthState = 'ok' | 'loading' | 'error'

const COLOR: Record<HealthState, string> = {
  ok: 'bg-pos shadow-pos',
  loading: 'bg-warn shadow-warn animate-pulse2',
  error: 'bg-neg shadow-neg',
}

export function StatusDot({ state, label }: { state: HealthState; label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 font-mono text-[11px] tabular-nums text-txtDim">
      <span
        data-testid="status-dot"
        data-state={state}
        className={`h-2 w-2 rounded-full shadow-[0_0_8px] ${COLOR[state]}`}
      />
      {label}
    </span>
  )
}
