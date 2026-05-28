import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

vi.mock('../auth/AuthContext', () => ({ useAuth: vi.fn() }))

import { useAuth } from '../auth/AuthContext'
import { RequireAuth } from './RequireAuth'

const mockUseAuth = vi.mocked(useAuth)

beforeEach(() => mockUseAuth.mockReset())

describe('RequireAuth', () => {
  it('redirects anonymous users to /login', () => {
    mockUseAuth.mockReturnValue({ status: 'anon', me: null, login: vi.fn(), logout: vi.fn() })
    render(
      <MemoryRouter initialEntries={['/secret']}>
        <Routes>
          <Route
            path="/secret"
            element={
              <RequireAuth>
                <div>SECRET</div>
              </RequireAuth>
            }
          />
          <Route path="/login" element={<div>LOGIN PAGE</div>} />
        </Routes>
      </MemoryRouter>,
    )
    expect(screen.getByText('LOGIN PAGE')).toBeInTheDocument()
    expect(screen.queryByText('SECRET')).toBeNull()
  })

  it('renders children when authed', () => {
    mockUseAuth.mockReturnValue({ status: 'authed', me: null, login: vi.fn(), logout: vi.fn() })
    render(
      <MemoryRouter>
        <RequireAuth>
          <div>SECRET</div>
        </RequireAuth>
      </MemoryRouter>,
    )
    expect(screen.getByText('SECRET')).toBeInTheDocument()
  })
})
