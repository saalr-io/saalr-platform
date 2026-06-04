import type React from 'react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { getToken, setToken } from '../lib/tokenStore'

const h = vi.hoisted(() => ({
  clerk: {
    isLoaded: true,
    isSignedIn: true,
    getToken: vi.fn(async () => 'clerk-jwt'),
    signOut: vi.fn(),
  },
  getMe: vi.fn(),
}))

vi.mock('@clerk/clerk-react', () => ({
  ClerkProvider: ({ children }: { children: React.ReactNode }) => children,
  useAuth: () => h.clerk,
  SignIn: () => null,
}))

vi.mock('../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/api')>()
  return { ...actual, getMe: h.getMe }
})

import { ClerkAuthProvider } from './ClerkAuthProvider'
import { useAuth } from './context'

function Probe() {
  const { status, me, logout } = useAuth()
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="tenant">{me?.tenant.display_name ?? ''}</span>
      <button onClick={() => logout()}>logout</button>
    </div>
  )
}

const ME = {
  user: { id: 'u1', email: 'alice@acme.com' },
  tenant: { id: 't1', display_name: 'acme', country_code: 'US' },
  tier: 'pro', entitlements: {},
}

beforeEach(() => {
  vi.stubEnv('VITE_CLERK_PUBLISHABLE_KEY', 'pk_test_x')
  vi.stubEnv('VITE_CLERK_JWT_TEMPLATE', 'saalr')
  h.clerk.isLoaded = true
  h.clerk.isSignedIn = true
  h.clerk.getToken.mockResolvedValue('clerk-jwt')
  h.clerk.signOut.mockReset()
  h.getMe.mockReset()
  setToken(null)
})
afterEach(() => vi.unstubAllEnvs())

describe('ClerkAuthProvider', () => {
  it('signed in: fetches a templated token, stores it, loads me, status authed', async () => {
    h.getMe.mockResolvedValue(ME)
    render(<ClerkAuthProvider><Probe /></ClerkAuthProvider>)
    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('authed'))
    expect(h.clerk.getToken).toHaveBeenCalledWith({ template: 'saalr' })
    expect(getToken()).toBe('clerk-jwt')
    expect(h.getMe).toHaveBeenCalled()
    expect(screen.getByTestId('tenant').textContent).toBe('acme')
  })

  it('getMe rejection: clears the token and falls back to anon (no throw)', async () => {
    h.getMe.mockRejectedValue(new Error('unauthorized'))
    render(<ClerkAuthProvider><Probe /></ClerkAuthProvider>)
    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('anon'))
    expect(getToken()).toBeNull()
  })

  it('signed out: status anon and does not call getMe', async () => {
    h.clerk.isSignedIn = false
    render(<ClerkAuthProvider><Probe /></ClerkAuthProvider>)
    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('anon'))
    expect(h.getMe).not.toHaveBeenCalled()
  })

  it('not loaded: status loading', () => {
    h.clerk.isLoaded = false
    render(<ClerkAuthProvider><Probe /></ClerkAuthProvider>)
    expect(screen.getByTestId('status').textContent).toBe('loading')
  })

  it('logout calls Clerk signOut and clears the token', async () => {
    h.getMe.mockResolvedValue(ME)
    render(<ClerkAuthProvider><Probe /></ClerkAuthProvider>)
    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('authed'))
    fireEvent.click(screen.getByText('logout'))
    await waitFor(() => expect(h.clerk.signOut).toHaveBeenCalled())
    expect(getToken()).toBeNull()
  })

  it('throws a clear error when the publishable key is missing', () => {
    vi.stubEnv('VITE_CLERK_PUBLISHABLE_KEY', '')
    expect(() => render(<ClerkAuthProvider><Probe /></ClerkAuthProvider>)).toThrow(/VITE_CLERK_PUBLISHABLE_KEY/)
  })
})
