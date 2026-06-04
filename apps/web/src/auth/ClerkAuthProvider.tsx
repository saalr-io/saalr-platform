import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { ClerkProvider, useAuth as useClerkAuth } from '@clerk/clerk-react'
import { getMe, type Me } from '../lib/api'
import { setToken } from '../lib/tokenStore'
import { AuthContext, type AuthStatus } from './context'

const REFRESH_MS = 50_000

function tokenOpts(template: string): { template: string } | undefined {
  return template ? { template } : undefined
}

function ClerkBridge({ template, children }: { template: string; children: ReactNode }) {
  const { isLoaded, isSignedIn, getToken, signOut } = useClerkAuth()
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [me, setMe] = useState<Me | null>(null)

  const sync = useCallback(async () => {
    if (!isLoaded) {
      setStatus('loading')
      return
    }
    if (!isSignedIn) {
      setToken(null)
      setMe(null)
      setStatus('anon')
      return
    }
    const t = await getToken(tokenOpts(template))
    if (!t) {
      setToken(null)
      setMe(null)
      setStatus('anon')
      return
    }
    // Persisted to tokenStore (localStorage) for the synchronous authHeaders(); on next boot
    // it may be momentarily stale until this sync() runs, but getMe()'s 401 path re-clears it.
    setToken(t)
    try {
      setMe(await getMe())
      setStatus('authed')
    } catch (err) {
      setToken(null)
      setMe(null)
      setStatus('anon')
      // getMe() throws Error('unauthorized') on a 401 — the likeliest cause is a JWT template
      // missing the `email` claim. Only hint on that case, not on 500s / network errors.
      if (err instanceof Error && err.message === 'unauthorized') {
        console.warn(
          'Clerk sign-in succeeded but /me returned 401 — check that the Clerk JWT template includes an `email` claim.',
        )
      }
    }
  }, [isLoaded, isSignedIn, getToken, template])

  useEffect(() => {
    void sync()
  }, [sync])

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return
    const id = setInterval(() => {
      void getToken(tokenOpts(template)).then((t) => {
        if (t) setToken(t)
      })
    }, REFRESH_MS)
    return () => clearInterval(id)
  }, [isLoaded, isSignedIn, getToken, template])

  const logout = useCallback(() => {
    setToken(null)
    setMe(null)
    setStatus('anon')
    void signOut()
  }, [signOut])

  const disabled = useCallback(async (): Promise<never> => {
    throw new Error('magic-link auth is disabled under Clerk')
  }, [])

  return (
    <AuthContext.Provider
      value={{
        status,
        me,
        login: () => disabled(),
        requestLink: () => disabled(),
        completeLink: () => disabled(),
        logout,
        refresh: sync,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function ClerkAuthProvider({ children }: { children: ReactNode }) {
  const pk = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY
  if (!pk) {
    throw new Error('VITE_CLERK_PUBLISHABLE_KEY is required when VITE_AUTH_PROVIDER=clerk')
  }
  const template = import.meta.env.VITE_CLERK_JWT_TEMPLATE ?? 'saalr'
  return (
    <ClerkProvider publishableKey={pk}>
      <ClerkBridge template={template}>{children}</ClerkBridge>
    </ClerkProvider>
  )
}
