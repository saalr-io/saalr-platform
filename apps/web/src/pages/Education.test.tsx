import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Education } from './Education'

vi.mock('../features/academy/hooks', () => ({
  useModules: () => ({
    data: {
      modules: [
        { slug: 'what-is-an-option', title: 'What is an option?', summary: 's', order: 10, minTier: 'free', estMinutes: 5 },
        { slug: 'volatility-surface', title: 'The volatility surface', summary: 's', order: 70, minTier: 'free', estMinutes: 6 },
      ],
      completed: 0, total: 2,
    },
    isLoading: false,
  }),
}))
vi.mock('../features/academy/ModuleReader', () => ({ ModuleReader: ({ slug }: { slug: string }) => <div data-testid="reader-slug">{slug}</div> }))
vi.mock('../features/academy/ModuleList', () => ({ ModuleList: () => <div /> }))
vi.mock('../features/academy/SearchBox', () => ({ SearchBox: () => <div /> }))
vi.mock('../features/academy/AskAssistant', () => ({ AskAssistant: () => <div /> }))

function wrap(initial: string) {
  return render(<MemoryRouter initialEntries={[initial]}><Education /></MemoryRouter>)
}

describe('Education deep-link', () => {
  it('opens the lesson named in ?lesson=', () => {
    wrap('/?lesson=volatility-surface')
    expect(screen.getByTestId('reader-slug').textContent).toBe('volatility-surface')
  })

  it('falls back to the first lesson without the param', () => {
    wrap('/')
    expect(screen.getByTestId('reader-slug').textContent).toBe('what-is-an-option')
  })
})
