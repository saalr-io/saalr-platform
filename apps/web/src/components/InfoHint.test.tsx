import type React from 'react'
import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { InfoHint } from './InfoHint'

const wrap = (ui: React.ReactNode) => render(<MemoryRouter>{ui}</MemoryRouter>)

describe('InfoHint', () => {
  it('opens the popover on click and shows title + body', () => {
    wrap(<InfoHint title="IV smile" body="Implied vol by strike." />)
    expect(screen.queryByTestId('info-hint-popover')).toBeNull()
    fireEvent.click(screen.getByTestId('info-hint'))
    const pop = screen.getByTestId('info-hint-popover')
    expect(pop.textContent).toContain('IV smile')
    expect(pop.textContent).toContain('Implied vol by strike.')
  })

  it('renders a learn-more link (react-router) when a target is provided', () => {
    wrap(<InfoHint title="t" body="b" learnMoreTo="/education?lesson=volatility-surface" />)
    fireEvent.click(screen.getByTestId('info-hint'))
    expect(screen.getByText(/learn more/i).getAttribute('href')).toBe('/education?lesson=volatility-surface')
  })

  it('omits the link when no target is given', () => {
    wrap(<InfoHint title="t" body="b" />)
    fireEvent.click(screen.getByTestId('info-hint'))
    expect(screen.queryByText(/learn more/i)).toBeNull()
  })

  it('closes on Escape', () => {
    wrap(<InfoHint title="t" body="b" />)
    fireEvent.click(screen.getByTestId('info-hint'))
    expect(screen.getByTestId('info-hint-popover')).toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByTestId('info-hint-popover')).toBeNull()
  })
})
