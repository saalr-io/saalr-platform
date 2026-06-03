import { useState } from 'react'
import { Markdown } from '../academy/markdown'
import { useTranscript } from './hooks'
import { formatUsd } from '../../lib/research'
import type { ResearchNote, Sentiment, VolForecast } from '../../lib/research'

// ── signal card helpers ────────────────────────────────────────────────────

function sentimentColor(label: string): string {
  const l = label.toLowerCase()
  if (l === 'bullish' || l === 'positive') return 'text-pos'
  if (l === 'bearish' || l === 'negative') return 'text-neg'
  return 'text-txtDim'
}

function SignalCard({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-line bg-panel2 px-3 py-2">
      <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-txtFaint">
        {label}
      </span>
      {children}
    </div>
  )
}

function SpotCard({ spot }: { spot: number }) {
  return (
    <SignalCard label="Spot">
      <span className="tnum font-mono text-base font-semibold text-txt">
        ${spot.toFixed(2)}
      </span>
    </SignalCard>
  )
}

function VolCard({ vf }: { vf: VolForecast | null }) {
  if (!vf) {
    return (
      <SignalCard label="Vol forecast">
        <span className="font-mono text-sm text-txtFaint">—</span>
      </SignalCard>
    )
  }
  return (
    <SignalCard label="Vol forecast">
      <span className="tnum font-mono text-base font-semibold text-txt">
        {(vf.primary_forecast * 100).toFixed(1)}%
      </span>
      <span className="text-[10px] text-txtFaint">
        {vf.horizon}d horizon · {vf.status}
      </span>
    </SignalCard>
  )
}

function SentimentCard({ s }: { s: Sentiment | null }) {
  if (!s) {
    return (
      <SignalCard label="Sentiment">
        <span className="font-mono text-sm text-txtFaint">—</span>
      </SignalCard>
    )
  }
  return (
    <SignalCard label="Sentiment">
      <span className={`text-sm font-semibold ${sentimentColor(s.label)}`}>
        {s.label}
      </span>
      <span className="tnum text-[10px] text-txtFaint">
        score {s.score.toFixed(2)}{s.confident ? ' · confident' : ''} · as of {s.as_of}
      </span>
    </SignalCard>
  )
}

// ── transcript ─────────────────────────────────────────────────────────────

function TranscriptPanel({ noteId }: { noteId: string }) {
  const { data, isLoading, error } = useTranscript(noteId, true)

  if (isLoading) {
    return (
      <div className="animate-pulse space-y-2">
        {[1, 2, 3].map((n) => (
          <div key={n} className="h-8 rounded bg-panel2" />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <p className="text-[11px] text-txtFaint" data-testid="transcript-error">
        {error.message === 'RESOURCE_NOT_FOUND'
          ? 'No transcript available for this note.'
          : 'Failed to load transcript.'}
      </p>
    )
  }

  if (!data || data.steps.length === 0) {
    return (
      <p className="text-[11px] text-txtFaint" data-testid="transcript-empty">
        No steps recorded.
      </p>
    )
  }

  return (
    <ol className="space-y-2" data-testid="transcript-steps">
      {data.steps.map((step, i) => {
        const tokens =
          step.prompt_tokens != null && step.completion_tokens != null
            ? step.prompt_tokens + step.completion_tokens
            : null
        return (
          <li
            key={i}
            className="rounded-lg border border-lineSoft bg-panel px-3 py-2 text-xs"
            data-testid={`step-${i}`}
          >
            <div className="flex items-baseline gap-2">
              <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-accent">
                {step.role}
              </span>
              {step.model && (
                <span className="font-mono text-[10px] text-txtFaint">
                  {step.model}
                  {tokens != null ? ` · ${tokens} tokens` : ''}
                  {step.cost_usd != null ? ` · ${formatUsd(step.cost_usd)}` : ''}
                </span>
              )}
            </div>
            <p className="mt-1 text-txtDim">{step.memo}</p>
          </li>
        )
      })}
    </ol>
  )
}

// ── main component ─────────────────────────────────────────────────────────

interface NoteViewProps {
  note: ResearchNote
}

export function NoteView({ note }: NoteViewProps) {
  const [showTranscript, setShowTranscript] = useState(false)

  const totalTokens = note.usage.prompt_tokens + note.usage.completion_tokens

  return (
    <div className="animate-fadeUp space-y-5" data-testid="note-view">
      {/* header */}
      <div className="flex flex-wrap items-baseline gap-3">
        <span className="font-mono text-xl font-semibold tracking-tight text-txt">
          {note.ticker}
        </span>
        <span className="text-[11px] text-txtFaint">
          {new Date(note.created_at).toLocaleString('en-US', {
            month: 'short', day: 'numeric', year: 'numeric',
            hour: '2-digit', minute: '2-digit',
          })}
        </span>
        {note.cached && (
          <span className="rounded border border-line bg-panel px-2 py-0.5 font-mono text-[10px] text-txtFaint">
            cached
          </span>
        )}
      </div>

      <div className="h-px bg-line" />

      {/* summary */}
      <div data-testid="note-summary">
        <Markdown source={note.summary} />
      </div>

      <div className="h-px bg-lineSoft" />

      {/* signal cards */}
      <div data-testid="signal-cards">
        <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.14em] text-txtFaint">
          Signals
        </p>
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-3">
          <SpotCard spot={note.signals.spot} />
          <VolCard vf={note.signals.vol_forecast} />
          <SentimentCard s={note.signals.sentiment} />
        </div>
      </div>

      {/* sources */}
      {note.sources.length > 0 && (
        <div data-testid="note-sources">
          <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.14em] text-txtFaint">
            Sources
          </p>
          <div className="flex flex-wrap gap-2">
            {note.sources.map((src) => (
              <span
                key={src.slug}
                className="rounded border border-line bg-panel2 px-2 py-1 text-[11px] text-txtDim"
              >
                {src.title}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* footer */}
      <p className="font-mono text-[10px] text-txtFaint" data-testid="note-footer">
        via {note.model} · {totalTokens} tokens · {formatUsd(note.cost_usd)}
      </p>

      <div className="h-px bg-lineSoft" />

      {/* transcript toggle */}
      <div>
        <button
          data-testid="transcript-toggle"
          onClick={() => setShowTranscript((v) => !v)}
          className="text-[11px] text-accent transition hover:text-accent/70"
        >
          {showTranscript ? 'Hide agent transcript' : 'View agent transcript'}
        </button>

        {showTranscript && (
          <div className="mt-3" data-testid="transcript-panel">
            <TranscriptPanel noteId={note.note_id} />
          </div>
        )}
      </div>
    </div>
  )
}
