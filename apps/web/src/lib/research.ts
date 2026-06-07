import { BASE, authHeaders } from './api'
import { setToken } from './tokenStore'
import { EntitlementError } from './strategies'

// Re-export so feature code only needs one import
export { EntitlementError }

// ── types ──────────────────────────────────────────────────────────────────

export type NoteStatus = 'queued' | 'running' | 'succeeded' | 'failed'
export type Market = 'US'

export interface VolForecast {
  horizon: number
  primary_forecast: number
  status: string
}

export interface Sentiment {
  score: number
  label: string
  confident: boolean
  as_of: string
}

export interface Signals {
  spot: number
  vol_forecast: VolForecast | null
  sentiment: Sentiment | null
}

export interface SourceRef {
  slug: string
  title: string
}

export interface Usage {
  prompt_tokens: number
  completion_tokens: number
}

export interface ResearchNote {
  note_id: string
  ticker: string
  market: Market
  summary: string
  signals: Signals
  sources: SourceRef[]
  model: string
  usage: Usage
  cost_usd: string | null // serialized as a string (Decimal) on the wire; null if unmetered
  status: 'succeeded'
  cached?: boolean
  created_at: string
}

export interface AcceptedRun {
  note_id: string
  status: 'queued' | 'running'
  poll_url: string
}

// Discriminated union returned from runResearch
export type RunResponse = ResearchNote | AcceptedRun

export interface NoteSummaryRow {
  note_id: string
  ticker: string
  market: Market
  model: string
  cost_usd: string | null
  created_at: string
}

// Poll response shapes
export interface NoteQueued { note_id: string; status: 'queued' | 'running' }
export interface NoteFailed { note_id: string; status: 'failed'; error: { code: string; message: string } }
export type NotePollResult = NoteQueued | NoteFailed | ResearchNote

export interface TranscriptStep {
  role: string
  memo: string
  provider?: string
  model?: string
  prompt_tokens?: number
  completion_tokens?: number
  cost_usd?: string | null
}

export interface Transcript {
  note_id: string
  steps: TranscriptStep[]
}

// Cost values arrive as strings (Decimal) or null; format defensively for display.
export function formatUsd(value: string | number | null | undefined, digits = 4): string {
  return value == null ? '—' : `$${Number(value).toFixed(digits)}`
}

// ── internal request wrapper ───────────────────────────────────────────────

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(init?.headers ?? {}) },
  })
  if (res.status === 401) {
    setToken(null)
    throw new Error('unauthorized')
  }
  if (res.status === 402) {
    const body = await res.json().catch(() => ({}))
    throw new EntitlementError(body?.detail?.error?.code ?? 'ENTITLEMENT_REQUIRED')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body?.detail?.error?.code ?? `request failed: ${res.status}`)
  }
  return (await res.json()) as T
}

// ── public API ─────────────────────────────────────────────────────────────

export function runResearch(params: {
  ticker: string
  market?: Market
  refresh?: boolean
}): Promise<RunResponse> {
  return request('/research/run', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}

export function listNotes(cursor?: string): Promise<{ notes: NoteSummaryRow[]; next_cursor: string | null }> {
  const qs = cursor ? `?limit=20&cursor=${encodeURIComponent(cursor)}` : '?limit=20'
  return request(`/research/notes${qs}`)
}

export function getNote(noteId: string): Promise<NotePollResult> {
  return request(`/research/notes/${encodeURIComponent(noteId)}`)
}

export function getTranscript(noteId: string): Promise<Transcript> {
  return request(`/research/notes/${encodeURIComponent(noteId)}/transcript`)
}
