import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { AuthProvider, useAuth } from './AuthContext'
import { setToken } from '../lib/tokenStore'

function Probe() {
  const { status, me, login, logout } = useAuth()
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="tenant">{me?.tenant.display_name ?? ''}</span>
      <button onClick={() => void login('alice@acme.com')}>login</button>
      <button onClick={() => logout()}>logout</button>
    </div>
  )
}

afterEach(() => setToken(null))

describe('useAuth (dev provider)', () => {
  it('logs in, exposes me, then logs out', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: RequestInfo | URL) => {
        if (String(url).endsWith('/auth/dev/login')) {
          return new Response(JSON.stringify({ token: 'dev:alice@acme.com' }), { status: 200 })
        }
        return new Response(
          JSON.stringify({
            user: { id: 'u1', email: 'alice@acme.com' },
            tenant: { id: 't1', display_name: 'alice', country_code: 'US' },
            tier: 'free',
            entitlements: { brokers: 0 },
          }),
          { status: 200 },
        )
      }),
    )

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('anon'))
    fireEvent.click(screen.getByText('login'))
    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('authed'))
    expect(screen.getByTestId('tenant').textContent).toBe('alice')

    fireEvent.click(screen.getByText('logout'))
    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('anon'))
  })

  it('exposes a refresh() on the context', async () => {
    let ctx: ReturnType<typeof useAuth> | null = null
    function Probe() { ctx = useAuth(); return null }
    render(<AuthProvider><Probe /></AuthProvider>)
    await waitFor(() => expect(ctx).not.toBeNull())
    expect(typeof ctx!.refresh).toBe('function')
  })
})
