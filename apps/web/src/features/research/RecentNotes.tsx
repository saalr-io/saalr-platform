import { formatUsd } from '../../lib/research'
import { useRecentNotes } from './hooks'

// ── props ──────────────────────────────────────────────────────────────────

interface RecentNotesProps {
  activeNoteId: string | null
  onSelect: (noteId: string) => void
}

// ── helpers ────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

// ── component ──────────────────────────────────────────────────────────────

export function RecentNotes({ activeNoteId, onSelect }: RecentNotesProps) {
  const { data, isLoading, error } = useRecentNotes()

  if (isLoading) {
    return (
      <div className="animate-pulse space-y-2" data-testid="recent-notes-loading">
        {[1, 2, 3].map((n) => (
          <div key={n} className="h-10 rounded-lg bg-panel2" />
        ))}
      </div>
    )
  }

  if (error) {
    // Premium gate is handled at the page level; show nothing here
    return null
  }

  const notes = data?.notes ?? []

  if (notes.length === 0) {
    return (
      <p className="text-[11px] text-txtFaint" data-testid="recent-notes-empty">
        No recent notes. Generate one above.
      </p>
    )
  }

  return (
    <div className="space-y-1" data-testid="recent-notes">
      <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-txtFaint">
        Recent notes
      </p>
      {notes.map((row) => {
        const isActive = row.note_id === activeNoteId
        return (
          <button
            key={row.note_id}
            data-testid={`note-row-${row.note_id}`}
            onClick={() => onSelect(row.note_id)}
            className={`flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left transition ${
              isActive
                ? 'border-accent/40 bg-accent/5 text-txt'
                : 'border-line bg-panel text-txtDim hover:border-accent/30 hover:text-txt'
            }`}
          >
            <div className="flex flex-col gap-0.5">
              <span className="font-mono text-xs font-semibold tracking-wide">{row.ticker}</span>
              <span className="text-[10px] text-txtFaint">{formatDate(row.created_at)}</span>
            </div>
            <span className="tnum font-mono text-[10px] text-txtFaint">
              {formatUsd(row.cost_usd, 3)}
            </span>
          </button>
        )
      })}
    </div>
  )
}
