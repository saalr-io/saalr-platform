import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Hero } from './Hero'
import { HERO } from './copy'

describe('Hero', () => {
  it('renders the headline in an <h1>, the tagline, and both CTAs', () => {
    render(<Hero />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(HERO.headline)
    expect(screen.getByText(HERO.tagline)).toBeInTheDocument()

    expect(screen.getByRole('link', { name: new RegExp(HERO.primary.label) })).toHaveAttribute(
      'href',
      '/app',
    )
    expect(screen.getByRole('link', { name: new RegExp(HERO.secondary.label) })).toHaveAttribute(
      'href',
      '/learn',
    )
  })

  it('shows the terminal kicker', () => {
    render(<Hero />)
    expect(screen.getByText(new RegExp(HERO.kicker))).toBeInTheDocument()
  })
})
