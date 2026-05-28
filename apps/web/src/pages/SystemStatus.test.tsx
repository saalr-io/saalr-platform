import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SystemStatus } from './SystemStatus'

function renderWithClient() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <SystemStatus />
    </QueryClientProvider>,
  )
}

describe('SystemStatus', () => {
  it('shows operational + connected on healthy API', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ status: 'ok', db: 'ok' }), { status: 200 })),
    )
    renderWithClient()
    await waitFor(() => expect(screen.getByText(/operational/i)).toBeInTheDocument())
    expect(screen.getByText(/connected/i)).toBeInTheDocument()
  })

  it('shows unreachable on API error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('x', { status: 503 })),
    )
    renderWithClient()
    await waitFor(() => expect(screen.getByText(/unreachable/i)).toBeInTheDocument())
  })
})