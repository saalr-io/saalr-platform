import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Logo, LogoMark } from './Logo'

describe('Logo', () => {
  it('renders an accessible mark and the serif wordmark', () => {
    render(<Logo />)
    expect(screen.getByRole('img', { name: 'Saalr' })).toBeInTheDocument()
    expect(screen.getByText('Saalr')).toBeInTheDocument()
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
