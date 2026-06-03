import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  askAssistant, completeModule, getModule, getProgress,
  listModules, searchContent,
  type AskAnswer, type ModuleDetail, type ModulesResponse,
  type ProgressResponse, type SearchResponse,
} from '../../lib/content'

// ── query keys ─────────────────────────────────────────────────────────────

export const KEYS = {
  modules: ['academy', 'modules'] as const,
  module: (slug: string) => ['academy', 'module', slug] as const,
  progress: ['academy', 'progress'] as const,
  search: (q: string) => ['academy', 'search', q] as const,
} as const

// ── hooks ──────────────────────────────────────────────────────────────────

export function useModules() {
  return useQuery<ModulesResponse>({
    queryKey: KEYS.modules,
    queryFn: listModules,
  })
}

export function useModule(slug: string) {
  return useQuery<ModuleDetail>({
    queryKey: KEYS.module(slug),
    queryFn: () => getModule(slug),
    enabled: slug.length > 0,
    retry: false,
  })
}

export function useProgress() {
  return useQuery<ProgressResponse>({
    queryKey: KEYS.progress,
    queryFn: getProgress,
  })
}

export function useComplete() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (slug: string) => completeModule(slug),
    onSuccess: (_data, slug) => {
      void qc.invalidateQueries({ queryKey: KEYS.modules })
      void qc.invalidateQueries({ queryKey: KEYS.progress })
      void qc.invalidateQueries({ queryKey: KEYS.module(slug) })
    },
  })
}

export function useSearch(q: string) {
  return useQuery<SearchResponse>({
    queryKey: KEYS.search(q),
    queryFn: () => searchContent(q),
    enabled: q.trim().length > 0,
    staleTime: 30_000,
  })
}

export function useAsk() {
  return useMutation<AskAnswer, Error, { question: string; k?: number }>({
    mutationFn: ({ question, k }) => askAssistant(question, k),
  })
}
