import { useTemplates, useBuildTemplate } from './hooks'
import type { StrategyConfig } from '../../lib/strategies'

const CATS: Array<'bullish' | 'bearish' | 'neutral'> = ['bullish', 'bearish', 'neutral']

export function TemplatePicker({
  underlying, expiry, atmStrike, onApply,
}: {
  underlying: string; expiry: string; atmStrike: number; onApply: (c: StrategyConfig) => void
}) {
  const { data: templates = [], isLoading } = useTemplates()
  const build = useBuildTemplate()

  function apply(key: string) {
    build.mutate(
      { key, params: { underlying, expiry, atm_strike: atmStrike } },
      { onSuccess: (cfg) => onApply(cfg) },
    )
  }

  if (isLoading) return <div className="text-xs text-txtFaint">Loading templates…</div>
  return (
    <div className="space-y-3">
      {CATS.map((cat) => (
        <div key={cat}>
          <div className="mb-1 font-mono text-[9px] uppercase tracking-wider text-txtFaint">{cat}</div>
          <div className="flex flex-wrap gap-2">
            {templates.filter((t) => t.category === cat).map((t) => (
              <button key={t.key} title={t.description} onClick={() => apply(t.key)}
                      className="rounded-full border border-line bg-panel px-3 py-1 text-xs text-txtDim hover:text-txt">
                {t.name}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
