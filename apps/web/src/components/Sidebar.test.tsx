import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Sidebar } from './Sidebar'

function renderSidebar() {
  return render(<MemoryRouter><Sidebar /></MemoryRouter>)
}

describe('Sidebar dev link', () => {
  afterEach(() => { vi.unstubAllEnvs() })

  it('shows the Dev Seed link in dev mode', () => {
    vi.stubEnv('DEV', true)
    renderSidebar()
    expect(screen.getByRole('link', { name: 'Dev Seed' })).toBeInTheDocument()
  })

  it('hides the Dev Seed link when not in dev mode', () => {
    vi.stubEnv('DEV', false)
    renderSidebar()
    expect(screen.queryByRole('link', { name: 'Dev Seed' })).toBeNull()
  })
})
