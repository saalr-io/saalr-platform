import { BASE, authHeaders } from './api'
import { setToken } from './tokenStore'
import { EntitlementError } from './strategies'

// Re-export so academy code only needs one import
export { EntitlementError }

// ── types ──────────────────────────────────────────────────────────────────

export type LessonStatus = 'not_started' | 'in_progress' | 'completed'
export type ContentTier = 'free' | 'pro' | 'premium'

export interface ModuleMeta {
  slug: string
  title: string
  summary: string
  order: number
  min_tier: ContentTier
  est_minutes: number
  locked: boolean
  status: LessonStatus
}

export interface ModuleDetail extends ModuleMeta {
  body: string
}

export interface ModulesResponse {
  modules: ModuleMeta[]
  completed: number
  in_progress: number
  total: number
}

export interface CompleteResponse {
  slug: string
  status: LessonStatus
  completed_at: string
}

export interface ProgressEntry {
  slug: string
  status: LessonStatus
  completed_at: string | null
}

export interface ProgressResponse {
  completed: number
  in_progress: number
  total: number
  modules: ProgressEntry[]
}

export interface SearchHit {
  slug: string
  title: string
  snippet: string
  score: number
  locked: boolean
}

export interface SearchResponse {
  results: SearchHit[]
}

export interface Citation {
  slug: string
  title: string
}

export interface AskUsage {
  prompt_tokens: number
  completion_tokens: number
}

export interface AskAnswer {
  answer: string
  citations: Citation[]
  model: string
  usage: AskUsage
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

export function listModules(): Promise<ModulesResponse> {
  return request('/content/modules')
}

export function getModule(slug: string): Promise<ModuleDetail> {
  return request(`/content/modules/${encodeURIComponent(slug)}`)
}

export function completeModule(slug: string): Promise<CompleteResponse> {
  return request(`/content/modules/${encodeURIComponent(slug)}/complete`, { method: 'POST' })
}

export function getProgress(): Promise<ProgressResponse> {
  return request('/content/progress')
}

export function searchContent(
  q: string,
  mode: 'hybrid' | 'semantic' | 'keyword' = 'hybrid',
  limit = 10,
): Promise<SearchResponse> {
  const params = new URLSearchParams({ q, mode, limit: String(limit) })
  return request(`/content/search?${params.toString()}`)
}

export function askAssistant(question: string, k?: number): Promise<AskAnswer> {
  return request('/content/ask', {
    method: 'POST',
    body: JSON.stringify({ question, ...(k !== undefined ? { k } : {}) }),
  })
}
