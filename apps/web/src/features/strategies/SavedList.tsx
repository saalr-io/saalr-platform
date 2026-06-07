import { useStrategies, useArchive } from './hooks'
import type { Strategy } from '../../lib/strategies'

export function SavedList({ onLoad }: { onLoad: (s: Strategy) => void }) {
  const { data, isLoading } = useStrategies()
  const archive = useArchive()
  if (isLoading) return <div className="text-xs text-txtFaint">Loading…</div>
  const items = data?.strategies ?? []
  if (items.length === 0) return <div className="text-xs text-txtFaint">No saved strategies yet.</div>
  return (
    <ul className="space-y-1">
      {items.map((s) => (
        <li key={s.strategy_id} className="flex items-center justify-between rounded border border-line bg-panel/50 px-3 py-2">
          <button className="text-left text-sm text-txt hover:underline" onClick={() => onLoad(s)}>{s.name}</button>
          <div className="flex items-center gap-2">
            <span className="rounded-full border border-line px-2 py-0.5 font-mono text-[9px] uppercase text-txtFaint">{s.state}</span>
            <button className="text-xs text-red-400" data-testid={`archive-${s.strategy_id}`}
                    onClick={() => archive.mutate(s.strategy_id)}>archive</button>
          </div>
        </li>
      ))}
    </ul>
  )
}
