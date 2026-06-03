import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Features } from './Features'
import { FEATURES } from './copy'

describe('Features', () => {
  it('renders every feature as a deep link', () => {
    render(<Features />)
    for (const f of FEATURES) {
      const link = screen.getByRole('link', { name: new RegExp(f.title) })
      expect(link).toHaveAttribute('href', f.href)
    }
  })
})
