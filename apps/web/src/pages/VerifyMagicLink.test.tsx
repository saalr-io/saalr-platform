import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

vi.mock('../auth/AuthContext', () => ({ useAuth: vi.fn() }))

import { useAuth } from '../auth/AuthContext'
import { VerifyMagicLink } from './VerifyMagicLink'

const mockUseAuth = vi.mocked(useAuth)

beforeEach(() => mockUseAuth.mockReset())

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/auth/verify" element={<VerifyMagicLink />} />
        <Route path="/" element={<div>HOME</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('VerifyMagicLink', () => {
  it('exchanges the token and navigates home', async () => {
    const completeLink = vi.fn().mockResolvedValue(undefined)
    mockUseAuth.mockReturnValue({
      status: 'anon',
      me: null,
      login: vi.fn(),
      requestLink: vi.fn(),
      completeLink,
      logout: vi.fn(),
    })
    renderAt('/auth/verify?token=abc')
    await waitFor(() => expect(screen.getByText('HOME')).toBeInTheDocument())
    expect(completeLink).toHaveBeenCalledWith('abc')
  })

  it('shows an error on an invalid link', async () => {
    const completeLink = vi.fn().mockRejectedValue(new Error('410'))
    mockUseAuth.mockReturnValue({
      status: 'anon',
      me: null,
      login: vi.fn(),
      requestLink: vi.fn(),
      completeLink,
      logout: vi.fn(),
    })
    renderAt('/auth/verify?token=bad')
    await waitFor(() =>
      expect(screen.getByText('This link is invalid or expired.')).toBeInTheDocument(),
    )
  })
})
