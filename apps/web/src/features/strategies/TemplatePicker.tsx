import type React from 'react'
import { useState } from 'react'
import { useTemplates, useBuildTemplate } from './hooks'
import type { StrategyConfig, TemplateDescriptor } from '../../lib/strategies'
import { InfoHint } from '../../components/InfoHint'
import { hintProps } from '../../content/helpHints'

type MV = TemplateDescriptor['market_view'] | 'all'
type VV = TemplateDescriptor['vol_view'] | 'all'

const MARKET_VIEWS: Array<{ key: MV; label: string }> = [
  { key: 'all', label: 'All' },
  { key: 'bullish', label: 'Bullish' },
  { key: 'bearish', label: 'Bearish' },
  { key: 'neutral', label: 'Neutral' },
  { key: 'volatile', label: 'Volatile' },
]
const VOL_VIEWS: Array<{ key: VV; label: string }> = [
  { key: 'all', label: 'All' },
  { key: 'long_vol', label: 'Long vol' },
  { key: 'short_vol', label: 'Short vol' },
]

export function TemplatePicker({
  underlying, expiry, atmStrike, onApply, onPick, selectedKey,
}: {
  underlying: string; expiry: string; atmStrike: number
  onApply: (c: StrategyConfig) => void
  onPick?: (key: string) => void
  selectedKey?: string
}) {
  const { data: templates = [], isLoading } = useTemplates()
  const build = useBuildTemplate()
  const [mv, setMv] = useState<MV>('all')
  const [vv, setVv] = useState<VV>('all')

  function apply(key: string) {
    onPick?.(key)
    build.mutate(
      { key, params: { underlying, expiry, atm_strike: atmStrike } },
      { onSuccess: (cfg) => onApply(cfg) },
    )
  }

  if (isLoading) return <div className="text-xs text-txtFaint">Loading templates…</div>

  const shown = templates.filter(
    (t) => (mv === 'all' || t.market_view === mv) && (vv === 'all' || t.vol_view === vv),
  )

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <FilterRow label="View" options={MARKET_VIEWS} value={mv} onChange={setMv} />
        <FilterRow label="Vol" options={VOL_VIEWS} value={vv} onChange={setVv} />
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {shown.map((t) => {
          const isSelected = t.key === selectedKey
          return (
          <div
            key={t.key}
            role="button"
            tabIndex={0}
            data-testid={`tpl-${t.key}`}
            data-selected={isSelected ? 'true' : undefined}
            onClick={() => apply(t.key)}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); apply(t.key) } }}
            title={t.description}
            className={`flex cursor-pointer flex-col gap-1.5 rounded-lg border p-3 text-left transition-colors ${
              isSelected ? 'border-accent bg-accent/10 ring-1 ring-accent/40' : 'border-line bg-panel hover:border-lineSoft'
            }`}
          >
            <div className="flex items-center justify-between gap-2">
              <span className={`text-[13px] font-medium ${isSelected ? 'text-accent' : 'text-txt'}`}>
                {isSelected ? '✓ ' : ''}{t.name}
              </span>
              <span className="flex items-center gap-1.5">
                <span className="font-mono text-[9px] uppercase tracking-wider text-txtFaint">{t.complexity}</span>
                <span onClick={(e) => e.stopPropagation()}><InfoHint {...hintProps(t.key)} /></span>
              </span>
            </div>
            <p className="text-[11px] leading-snug text-txtDim">{t.description}</p>
            <div className="flex flex-wrap gap-1.5">
              <Badge>{t.net}</Badge>
              <Badge>{t.legs} legs</Badge>
              <Badge tone={t.risk === 'undefined' ? 'warn' : undefined}>
                {t.risk === 'undefined' ? 'undefined risk' : 'defined risk'}
              </Badge>
            </div>
          </div>
          )
        })}
        {shown.length === 0 && (
          <p data-testid="tpl-empty" className="text-xs text-txtFaint">No templates match these filters.</p>
        )}
      </div>
    </div>
  )
}

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

function FilterRow<T extends string>({
  label, options, value, onChange,
}: {
  label: string; options: Array<{ key: T; label: string }>; value: T; onChange: (v: T) => void
}) {
  return (
    <div className="flex items-center gap-1">
      <span className="font-mono text-[9px] uppercase tracking-wider text-txtFaint">{label}</span>
      {options.map((o) => (
        <button
          key={o.key}
          onClick={() => onChange(o.key)}
          className={`rounded-full px-2 py-0.5 text-[11px] transition-colors ${
            value === o.key ? 'bg-accent text-canvas' : 'text-txtDim hover:text-txt'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
