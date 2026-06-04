import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('../auth/AuthContext', () => ({ useAuth: vi.fn() }))

import { useAuth } from '../auth/AuthContext'
import { Login } from './Login'

const mockUseAuth = vi.mocked(useAuth)

beforeEach(() => mockUseAuth.mockReset())

describe('Login', () => {
  it('sends a magic link and shows the dev link', async () => {
    const requestLink = vi
      .fn()
      .mockResolvedValue({ dev_link: 'http://localhost:5174/auth/verify?token=abc' })
    mockUseAuth.mockReturnValue({
      status: 'anon',
      me: null,
      login: vi.fn(),
      requestLink,
      completeLink: vi.fn(),
      logout: vi.fn(),
      refresh: vi.fn(),
    })

    render(<Login />)
    fireEvent.change(screen.getByPlaceholderText('you@example.com'), {
      target: { value: 'alice@acme.com' },
    })
    fireEvent.click(screen.getByText('Send magic link'))

    await waitFor(() => expect(screen.getByText('Check your email')).toBeInTheDocument())
    expect(requestLink).toHaveBeenCalledWith('alice@acme.com')
    const link = screen.getByText('Dev: open magic link') as HTMLAnchorElement
    expect(link.getAttribute('href')).toContain('/auth/verify?token=abc')
  })
})
