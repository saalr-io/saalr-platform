import { createContext, useContext } from 'react'
import type { Me } from '../lib/api'

export type AuthStatus = 'loading' | 'authed' | 'anon'

export interface AuthContextValue {
  status: AuthStatus
  me: Me | null
  login: (email?: string) => Promise<void>
  requestLink: (email: string) => Promise<{ dev_link?: string }>
  completeLink: (token: string) => Promise<void>
  logout: () => void
  refresh: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used within an AuthProvider')
  return value
}
