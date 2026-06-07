import type { ModuleMeta, LessonStatus } from '../../lib/content'

// ── helpers ────────────────────────────────────────────────────────────────

function statusDot(status: LessonStatus) {
  const cls =
    status === 'completed'
      ? 'bg-pos'
      : status === 'in_progress'
        ? 'bg-warn'
        : 'bg-line'
  return (
    <span
      aria-label={status}
      className={`h-1.5 w-1.5 shrink-0 rounded-[2px] ${cls}`}
    />
  )
}

function tierBadge(locked: boolean, minTier: ModuleMeta['min_tier']) {
  if (!locked) return null
  const label = minTier === 'premium' ? 'PREMIUM' : 'PRO'
  return (
    <span className="ml-auto shrink-0 rounded border border-accent/30 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.14em] text-accent">
      {label}
    </span>
  )
}

// ── component ──────────────────────────────────────────────────────────────

interface ModuleListProps {
  modules: ModuleMeta[]
  activeSlug: string | null
  onSelect: (slug: string) => void
}

export function ModuleList({ modules, activeSlug, onSelect }: ModuleListProps) {
  if (modules.length === 0) {
    return (
      <div className="px-2 py-4 text-[11px] text-txtFaint">No lessons found.</div>
    )
  }

  return (
    <div className="flex flex-col gap-px" role="list">
      {modules.map((m) => {
        const isActive = m.slug === activeSlug
        return (
          <button
            key={m.slug}
            role="listitem"
            data-testid={`module-row-${m.slug}`}
            onClick={() => onSelect(m.slug)}
            className={`group flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-left transition-colors ${
              isActive
                ? 'bg-panel text-txt'
                : 'text-txtDim hover:bg-panel/60 hover:text-txt'
            }`}
          >
            {/* order number */}
            <span className="w-5 shrink-0 font-mono text-[10px] text-txtFaint tnum">
              {String(m.order).padStart(2, '0')}
            </span>

            {/* status dot */}
            {statusDot(m.status)}

            {/* title + time */}
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[13px] font-medium leading-snug">
                {m.title}
              </span>
              <span className="font-mono text-[10px] text-txtFaint">
                {m.est_minutes} min
              </span>
            </span>

            {/* lock badge */}
            {tierBadge(m.locked, m.min_tier)}
          </button>
        )
      })}
    </div>
  )
}
