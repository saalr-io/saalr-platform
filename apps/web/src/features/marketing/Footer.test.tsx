import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Footer } from './Footer'
import { DISCLAIMER } from './copy'

describe('Footer', () => {
  it('renders nav links and the disclaimer', () => {
    render(<Footer />)
    expect(screen.getByRole('link', { name: 'Learn' })).toHaveAttribute('href', '/learn')
    expect(screen.getByRole('link', { name: 'Open app' })).toHaveAttribute('href', '/app')
    expect(screen.getByText(DISCLAIMER)).toBeInTheDocument()
  })
})
