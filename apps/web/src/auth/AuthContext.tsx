import {
  useCallback,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import { devLogin, getMe, requestMagicLink, verifyMagicLink, type Me } from '../lib/api'
import { getToken, setToken } from '../lib/tokenStore'
import { AuthContext, useAuth, type AuthStatus } from './context'
import { ClerkAuthProvider } from './ClerkAuthProvider'

export { useAuth }
export type { AuthStatus, AuthContextValue } from './context'

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
    <AuthContext.Provider value={{ status, me, login, requestLink, completeLink, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  )
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const provider = import.meta.env.VITE_AUTH_PROVIDER ?? 'dev'
  if (provider === 'clerk') {
    return <ClerkAuthProvider>{children}</ClerkAuthProvider>
  }
  return <DevAuthProvider>{children}</DevAuthProvider>
}
