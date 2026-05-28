import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import { devLogin, getMe, requestMagicLink, verifyMagicLink, type Me } from '../lib/api'
import { getToken, setToken } from '../lib/tokenStore'

export type AuthStatus = 'loading' | 'authed' | 'anon'

export interface AuthContextValue {
  status: AuthStatus
  me: Me | null
  login: (email?: string) => Promise<void>
  requestLink: (email: string) => Promise<{ dev_link?: string }>
  completeLink: (token: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used within an AuthProvider')
  return value
}

function DevAuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [me, setMe] = useState<Me | null>(null)

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setMe(null)
      setStatus('anon')
      return
    }
    try {
      setMe(await getMe())
      setStatus('authed')
    } catch {
      setToken(null)
      setMe(null)
      setStatus('anon')
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const login = useCallback(
    async (email?: string) => {
      const token = await devLogin(email ?? '')
      setToken(token)
      await refresh()
    },
    [refresh],
  )

  const requestLink = useCallback(async (email: string) => {
    return await requestMagicLink(email)
  }, [])

  const completeLink = useCallback(
    async (token: string) => {
      const sessionToken = await verifyMagicLink(token)
      setToken(sessionToken)
      await refresh()
    },
    [refresh],
  )

  const logout = useCallback(() => {
    setToken(null)
    setMe(null)
    setStatus('anon')
  }, [])

  return (
    <AuthContext.Provider value={{ status, me, login, requestLink, completeLink, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const provider = import.meta.env.VITE_AUTH_PROVIDER ?? 'dev'
  if (provider === 'clerk') {
    // The backend ClerkAuthProvider is implemented; the Clerk React SDK bridge
    // (ClerkProvider + getToken) is added once a publishable key is configured.
    throw new Error(
      'VITE_AUTH_PROVIDER=clerk is not yet wired on the frontend — add @clerk/clerk-react + a ClerkAuthProvider bridge',
    )
  }
  return <DevAuthProvider>{children}</DevAuthProvider>
}
