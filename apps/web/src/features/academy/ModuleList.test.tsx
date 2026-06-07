import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ModuleList } from './ModuleList'
import type { ModuleMeta } from '../../lib/content'

const FREE_MODULE: ModuleMeta = {
  slug: 'options-101', title: 'Options 101', summary: 'Intro', order: 1,
  min_tier: 'free', est_minutes: 10, locked: false, status: 'not_started',
}
const PRO_MODULE: ModuleMeta = {
  slug: 'greeks-deep', title: 'Greeks Deep Dive', summary: 'Greeks', order: 2,
  min_tier: 'pro', est_minutes: 20, locked: true, status: 'not_started',
}
const PREMIUM_MODULE: ModuleMeta = {
  slug: 'vol-arb', title: 'Vol Arb', summary: 'Volatility', order: 3,
  min_tier: 'premium', est_minutes: 30, locked: true, status: 'not_started',
}
const COMPLETED_MODULE: ModuleMeta = {
  slug: 'basics', title: 'Basics', summary: 'Basics', order: 4,
  min_tier: 'free', est_minutes: 5, locked: false, status: 'completed',
}
const IN_PROGRESS_MODULE: ModuleMeta = {
  slug: 'calls', title: 'Calls', summary: 'Calls', order: 5,
  min_tier: 'free', est_minutes: 8, locked: false, status: 'in_progress',
}

describe('ModuleList', () => {
  it('renders module titles', () => {
    render(<ModuleList modules={[FREE_MODULE]} activeSlug={null} onSelect={vi.fn()} />)
    expect(screen.getByText('Options 101')).toBeTruthy()
  })

  it('shows estimated minutes', () => {
    render(<ModuleList modules={[FREE_MODULE]} activeSlug={null} onSelect={vi.fn()} />)
    expect(screen.getByText('10 min')).toBeTruthy()
  })

  it('shows order number zero-padded', () => {
    render(<ModuleList modules={[FREE_MODULE]} activeSlug={null} onSelect={vi.fn()} />)
    expect(screen.getByText('01')).toBeTruthy()
  })

  it('shows PRO lock badge for pro-locked module', () => {
    render(<ModuleList modules={[PRO_MODULE]} activeSlug={null} onSelect={vi.fn()} />)
    expect(screen.getByText('PRO')).toBeTruthy()
  })

  it('shows PREMIUM lock badge for premium-locked module', () => {
    render(<ModuleList modules={[PREMIUM_MODULE]} activeSlug={null} onSelect={vi.fn()} />)
    expect(screen.getByText('PREMIUM')).toBeTruthy()
  })

  it('does NOT show lock badge for free unlocked module', () => {
    render(<ModuleList modules={[FREE_MODULE]} activeSlug={null} onSelect={vi.fn()} />)
    expect(screen.queryByText('PRO')).toBeNull()
    expect(screen.queryByText('PREMIUM')).toBeNull()
  })

  it('highlights the active slug', () => {
    render(<ModuleList modules={[FREE_MODULE]} activeSlug="options-101" onSelect={vi.fn()} />)
    const btn = screen.getByTestId('module-row-options-101')
    expect(btn.className).toContain('bg-panel')
  })

  it('calls onSelect with slug when clicked', () => {
    const onSelect = vi.fn()
    render(<ModuleList modules={[FREE_MODULE]} activeSlug={null} onSelect={onSelect} />)
    fireEvent.click(screen.getByTestId('module-row-options-101'))
    expect(onSelect).toHaveBeenCalledWith('options-101')
  })

  it('shows status dot aria-label for completed', () => {
    render(<ModuleList modules={[COMPLETED_MODULE]} activeSlug={null} onSelect={vi.fn()} />)
    expect(screen.getByLabelText('completed')).toBeTruthy()
  })

  it('shows status dot aria-label for in_progress', () => {
    render(<ModuleList modules={[IN_PROGRESS_MODULE]} activeSlug={null} onSelect={vi.fn()} />)
    expect(screen.getByLabelText('in_progress')).toBeTruthy()
  })

  it('shows empty state when modules list is empty', () => {
    render(<ModuleList modules={[]} activeSlug={null} onSelect={vi.fn()} />)
    expect(screen.getByText('No lessons found.')).toBeTruthy()
  })

  it('renders multiple modules', () => {
    render(
      <ModuleList
        modules={[FREE_MODULE, PRO_MODULE, PREMIUM_MODULE]}
        activeSlug={null}
        onSelect={vi.fn()}
      />,
    )
    expect(screen.getByText('Options 101')).toBeTruthy()
    expect(screen.getByText('Greeks Deep Dive')).toBeTruthy()
    expect(screen.getByText('Vol Arb')).toBeTruthy()
  })
})


