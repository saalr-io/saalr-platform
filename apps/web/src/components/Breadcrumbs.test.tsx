import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Breadcrumbs } from './Breadcrumbs'

function at(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Breadcrumbs />
    </MemoryRouter>,
  )
}

describe('Breadcrumbs', () => {
  it('renders nothing on the dashboard root', () => {
    const { container } = at('/')
    expect(container.querySelector('nav')).toBeNull()
  })

  it('renders a labelled nav with linked ancestors and a current page', () => {
    at('/billing/success')

    expect(screen.getByRole('navigation', { name: /breadcrumb/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Home' })).toHaveAttribute('href', '/')
    expect(screen.getByRole('link', { name: 'Billing' })).toHaveAttribute('href', '/billing')

    // The section crumb is plain text, not a link.
    expect(screen.queryByRole('link', { name: 'System' })).toBeNull()
    expect(screen.getByText('System')).toBeInTheDocument()

    // The current page is plain text marked aria-current and is not a link.
    expect(screen.queryByRole('link', { name: 'Success' })).toBeNull()
    expect(screen.getByText('Success')).toHaveAttribute('aria-current', 'page')
  })
})
