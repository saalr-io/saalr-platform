import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { MarketsGate } from './MarketsGate'

describe('MarketsGate', () => {
  it('links to billing to upgrade to Pro', () => {
    render(<MemoryRouter><MarketsGate /></MemoryRouter>)
    const link = screen.getByRole('link', { name: /upgrade to pro/i })
    expect(link).toHaveAttribute('href', '/billing?plan=pro')
  })
})
