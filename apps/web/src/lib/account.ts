import { BASE, authHeaders } from './api'

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
      ...(init?.headers ?? {}),
    },
  })
  if (!res.ok) throw new Error(`account ${res.status}`)
  return (await res.json()) as T
}

export function setOptIn(opt_in: boolean) {
  return req('/me/marketing/opt-in', { method: 'POST', body: JSON.stringify({ opt_in }) })
}

export function updateProfile(p: { preferred_tz?: string; preferred_locale?: string }) {
  return req('/me/profile', { method: 'PATCH', body: JSON.stringify(p) })
}

export function requestDeletion() {
  return req('/me/request-deletion', { method: 'POST' })
}
