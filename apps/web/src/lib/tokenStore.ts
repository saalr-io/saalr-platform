const KEY = 'saalr_token'

let token: string | null =
  typeof localStorage !== 'undefined' ? localStorage.getItem(KEY) : null

export function getToken(): string | null {
  return token
}

export function setToken(value: string | null): void {
  token = value
  if (typeof localStorage === 'undefined') return
  if (value) localStorage.setItem(KEY, value)
  else localStorage.removeItem(KEY)
}
