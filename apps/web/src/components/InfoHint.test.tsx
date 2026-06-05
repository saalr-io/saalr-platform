import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { InfoHint } from './InfoHint'

describe('InfoHint', () => {
  it('opens the popover on click and shows title + body', () => {
    render(<InfoHint title="IV smile" body="Implied vol by strike." />)
    expect(screen.queryByTestId('info-hint-popover')).toBeNull()
    fireEvent.click(screen.getByTestId('info-hint'))
    const pop = screen.getByTestId('info-hint-popover')
    expect(pop.textContent).toContain('IV smile')
    expect(pop.textContent).toContain('Implied vol by strike.')
  })

  it('renders a learn-more link when href is provided', () => {
    render(<InfoHint title="t" body="b" learnMoreHref="/app/education?lesson=volatility-surface" />)
    fireEvent.click(screen.getByTestId('info-hint'))
    expect(screen.getByText(/learn more/i).getAttribute('href')).toBe('/app/education?lesson=volatility-surface')
  })

  it('omits the link when no href is given', () => {
    render(<InfoHint title="t" body="b" />)
    fireEvent.click(screen.getByTestId('info-hint'))
    expect(screen.queryByText(/learn more/i)).toBeNull()
  })

  it('closes on Escape', () => {
    render(<InfoHint title="t" body="b" />)
    fireEvent.click(screen.getByTestId('info-hint'))
    expect(screen.getByTestId('info-hint-popover')).toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByTestId('info-hint-popover')).toBeNull()
  })
})
