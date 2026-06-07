import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Markdown } from './markdown'

describe('Markdown', () => {
  it('renders an h1 heading', () => {
    render(<Markdown source="# Hello World" />)
    expect(screen.getByText('Hello World').tagName).toBe('H2')
  })

  it('renders an h2 heading', () => {
    render(<Markdown source="## Section" />)
    expect(screen.getByText('Section').tagName).toBe('H3')
  })

  it('renders an h3 heading', () => {
    render(<Markdown source="### Subsection" />)
    expect(screen.getByText('Subsection').tagName).toBe('H4')
  })

  it('renders a paragraph', () => {
    render(<Markdown source="This is a paragraph." />)
    expect(screen.getByText('This is a paragraph.').tagName).toBe('P')
  })

  it('renders bold text', () => {
    render(<Markdown source="Some **bold** text" />)
    expect(screen.getByText('bold').tagName).toBe('STRONG')
  })

  it('renders italic text', () => {
    render(<Markdown source="Some *italic* text" />)
    expect(screen.getByText('italic').tagName).toBe('EM')
  })

  it('renders inline code', () => {
    render(<Markdown source="Use `delta` carefully" />)
    expect(screen.getByText('delta').tagName).toBe('CODE')
  })

  it('renders an unordered list', () => {
    render(<Markdown source={`- Item one\n- Item two\n- Item three`} />)
    expect(screen.getByText('Item one')).toBeTruthy()
    expect(screen.getByText('Item two')).toBeTruthy()
    expect(screen.getByText('Item three')).toBeTruthy()
  })

  it('renders an ordered list', () => {
    render(<Markdown source={`1. First\n2. Second`} />)
    expect(screen.getByText('First')).toBeTruthy()
    expect(screen.getByText('Second')).toBeTruthy()
    // numbers rendered as mono spans
    expect(screen.getByText('1.')).toBeTruthy()
    expect(screen.getByText('2.')).toBeTruthy()
  })

  it('renders a full lesson snippet without crashing', () => {
    const source = `# Options Basics

## What is a Call?

A **call option** gives the buyer the *right* to buy at the strike.

- Delta ranges from 0 to 1
- Gamma is the rate of delta change

1. Buy the option
2. Monitor delta
3. Roll or close
`
    const { container } = render(<Markdown source={source} />)
    expect(container.querySelector('h2')).toBeTruthy()
    expect(container.querySelector('h3')).toBeTruthy()
    expect(container.querySelector('strong')).toBeTruthy()
    expect(container.querySelector('em')).toBeTruthy()
    expect(container.querySelector('ul')).toBeTruthy()
    expect(container.querySelector('ol')).toBeTruthy()
  })
})
