import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { GlossaryTermArticle } from './GlossaryTermArticle'
import { GLOSSARY } from '../../../src/seo/content/glossary'

const theta = GLOSSARY.find((t) => t.slug === 'theta')!

describe('GlossaryTermArticle', () => {
  it('renders the answer-first definition in a geo-speakable element, plus references', () => {
    const { container } = render(<GlossaryTermArticle term={theta} origin="https://saalr.com" />)
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Theta')
    expect(container.querySelector('.geo-speakable')!.textContent).toContain(theta.short.slice(0, 20))
    const refs = Array.from(container.querySelectorAll('a[rel="noopener noreferrer"]'))
    expect(refs.length).toBeGreaterThanOrEqual(theta.sources.length)
    const ld = container.querySelector('script[type="application/ld+json"]')!.textContent!
    expect(ld).toContain('DefinedTerm')
    expect(ld).toContain('SpeakableSpecification')
  })
})
