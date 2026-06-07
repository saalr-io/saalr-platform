import { BASE, authHeaders } from './api'

export const ONBOARDING_STEPS = ['build_strategy', 'see_regime', 'paper_trade', 'read_lesson'] as const
export type OnboardingStep = (typeof ONBOARDING_STEPS)[number]
export interface Onboarding { steps: string[]; all_done: boolean }

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init, headers: { 'Content-Type': 'application/json', ...authHeaders(), ...(init?.headers ?? {}) },
  })
  if (!res.ok) throw new Error(`onboarding ${res.status}`)
  return (await res.json()) as T
}

export function getOnboarding(): Promise<Onboarding> { return req('/onboarding') }
export function completeStep(step: OnboardingStep): Promise<Onboarding> {
  return req('/onboarding/complete', { method: 'POST', body: JSON.stringify({ step }) })
}
