import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getNote, getTranscript, listNotes, runResearch,
  type NotePollResult, type NoteSummaryRow, type RunResponse, type Transcript,
} from '../../lib/research'

// ── query keys ─────────────────────────────────────────────────────────────

export const KEYS = {
  notes: ['research', 'notes'] as const,
  note: (id: string) => ['research', 'note', id] as const,
  transcript: (id: string) => ['research', 'transcript', id] as const,
} as const

// ── hooks ──────────────────────────────────────────────────────────────────

export function useRecentNotes(cursor?: string) {
  return useQuery<{ notes: NoteSummaryRow[]; next_cursor: string | null }>({
    queryKey: KEYS.notes,
    queryFn: () => listNotes(cursor),
    retry: false,
  })
}

export function useNote(noteId: string | null) {
  return useQuery<NotePollResult>({
    queryKey: KEYS.note(noteId ?? ''),
    queryFn: () => getNote(noteId!),
    enabled: !!noteId,
    retry: false,
    // Poll every 2 s until the note reaches a terminal state
    refetchInterval: (query) => {
      const s = query.state.data?.status
      return s === 'succeeded' || s === 'failed' ? false : 2000
    },
  })
}

export function useRunResearch() {
  const qc = useQueryClient()
  return useMutation<RunResponse, Error, { ticker: string; market?: 'US'; refresh?: boolean }>({
    mutationFn: runResearch,
    onSuccess: (data) => {
      // If we got a full succeeded note back (200 cache hit), seed the cache
      if (data.status === 'succeeded') {
        void qc.invalidateQueries({ queryKey: KEYS.notes })
      }
    },
  })
}

export function useTranscript(noteId: string | null, enabled: boolean) {
  return useQuery<Transcript>({
    queryKey: KEYS.transcript(noteId ?? ''),
    queryFn: () => getTranscript(noteId!),
    enabled: !!noteId && enabled,
    retry: false,
  })
}
