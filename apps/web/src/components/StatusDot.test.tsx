import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatusDot } from './StatusDot'

describe('StatusDot', () => {
  it('renders ok state with label', () => {
    render(<StatusDot state="ok" label="API live" />)
    expect(screen.getByText('API live')).toBeInTheDocument()
    expect(screen.getByTestId('status-dot')).toHaveAttribute('data-state', 'ok')
  })

  it('renders error state', () => {
    render(<StatusDot state="error" label="API unreachable" />)
    expect(screen.getByTestId('status-dot')).toHaveAttribute('data-state', 'error')
  })
})