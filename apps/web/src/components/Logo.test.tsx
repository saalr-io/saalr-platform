import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Logo, LogoMark } from './Logo'

describe('Logo', () => {
  it('renders the mono wordmark (mark is decorative — not double-announced)', () => {
    render(<Logo />)
    expect(screen.getByText('SAALR')).toBeInTheDocument()
    // The adjacent mark is aria-hidden, so it must NOT expose a second "Saalr" img.
    expect(screen.queryByRole('img', { name: 'Saalr' })).not.toBeInTheDocument()
  })

  it('shows the terminal descriptor when asked', () => {
    render(<Logo descriptor />)
    expect(screen.getByText(/RESEARCH/)).toBeInTheDocument()
  })

  it('LogoMark renders a standalone accessible mark', () => {
    render(<LogoMark />)
    expect(screen.getByRole('img', { name: 'Saalr' })).toBeInTheDocument()
  })
})
