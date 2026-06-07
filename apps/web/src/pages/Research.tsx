import { useState } from 'react'
import { EntitlementError } from '../lib/research'
import { useRecentNotes, useNote } from '../features/research/hooks'
import { PremiumGate } from '../features/research/PremiumGate'
import { RunForm } from '../features/research/RunForm'
import { RecentNotes } from '../features/research/RecentNotes'
import { NoteView } from '../features/research/NoteView'
import { NoteStatusPanel } from '../features/research/NoteStatusPanel'
import type { ResearchNote, NoteFailed } from '../lib/research'

// ── page ───────────────────────────────────────────────────────────────────

export function Research() {
  const [activeNoteId, setActiveNoteId] = useState<string | null>(null)
  const [cachedNote, setCachedNote] = useState<ResearchNote | null>(null)
  const [premiumBlocked, setPremiumBlocked] = useState(false)

  // Use recentNotes primarily to detect global premium gate
  const recentNotes = useRecentNotes()

  // Poll the active note when we don't already have the full note cached
  const pollEnabled = !!activeNoteId && !cachedNote
  const noteQuery = useNote(pollEnabled ? activeNoteId : null)

  // Detect premium gate from the notes list query error
  const notesError = recentNotes.error
  const isNotesGated =
    notesError instanceof EntitlementError &&
    notesError.code === 'ENTITLEMENT_RESEARCH_AGENT_REQUIRES_PREMIUM'

  if (premiumBlocked || isNotesGated) {
    return (
      <div className="animate-fadeUp space-y-6">
        <Header />
        <PremiumGate />
      </div>
    )
  }

  // Resolve what to show in the right pane
  function handleNote(note: ResearchNote) {
    setCachedNote(note)
    setActiveNoteId(note.note_id)
  }

  function handlePending(noteId: string) {
    setCachedNote(null)
    setActiveNoteId(noteId)
  }

  function handleSelect(noteId: string) {
    setCachedNote(null)
    setActiveNoteId(noteId)
  }

  // Determine the right-pane content
  const polledNote = noteQuery.data
  const displayNote: ResearchNote | null =
    cachedNote ??
    (polledNote?.status === 'succeeded' ? (polledNote as ResearchNote) : null)

  const pollingStatus =
    !displayNote && polledNote && polledNote.status !== 'succeeded'
      ? polledNote
      : null

  // Ticker shown in the status/running panel: the loaded note's ticker, else the id we're polling.
  const statusTicker = displayNote?.ticker ?? activeNoteId ?? ''

  return (
    <div className="animate-fadeUp space-y-6">
      <Header />

      <div className="grid gap-6 lg:grid-cols-[300px_1fr]">
        {/* ── left rail ── */}
        <div className="space-y-5">
          <RunForm
            onNote={handleNote}
            onPending={handlePending}
            onPremiumRequired={() => setPremiumBlocked(true)}
          />
          <div className="h-px bg-lineSoft" />
          <RecentNotes activeNoteId={activeNoteId} onSelect={handleSelect} />
        </div>

        {/* ── right pane ── */}
        <div className="rounded-lg border border-line bg-panel p-5">
          {displayNote ? (
            <NoteView note={displayNote} />
          ) : pollingStatus ? (
            pollingStatus.status === 'failed' ? (
              <NoteStatusPanel
                ticker={statusTicker}
                status="failed"
                errorMessage={(pollingStatus as NoteFailed).error?.message}
              />
            ) : (
              <NoteStatusPanel
                ticker={statusTicker}
                status={pollingStatus.status as 'queued' | 'running'}
              />
            )
          ) : noteQuery.isLoading && activeNoteId ? (
            <NoteStatusPanel ticker={statusTicker} status="running" />
          ) : (
            <div
              className="flex h-40 items-center justify-center text-[12px] text-txtFaint"
              data-testid="empty-hint"
            >
              Enter a ticker above to generate a research note.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── header ─────────────────────────────────────────────────────────────────

function Header() {
  return (
    <div className="flex flex-wrap items-baseline gap-3">
      <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">
        // Research Agent
      </p>
      <h2 className="text-xl font-semibold tracking-tight">AI-powered research notes</h2>
      <span className="rounded border border-accent/30 bg-accent/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-accent">
        Premium
      </span>
    </div>
  )
}
