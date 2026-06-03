import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AskAssistant } from './AskAssistant'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
}

const ANSWER_RESPONSE = {
  answer: 'Delta measures the rate of change of the option price.',
  citations: [{ slug: 'greeks', title: 'Greeks' }],
  model: 'gpt-4o',
  usage: { prompt_tokens: 10, completion_tokens: 20 },
}

describe('AskAssistant', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('renders the question input and submit button', () => {
    render(wrap(<AskAssistant />))
    expect(screen.getByTestId('ask-input')).toBeTruthy()
    expect(screen.getByTestId('ask-submit')).toBeTruthy()
  })

  it('submit button is disabled when input is empty', () => {
    render(wrap(<AskAssistant />))
    expect(screen.getByTestId('ask-submit')).toBeDisabled()
  })

  it('shows answer on success', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify(ANSWER_RESPONSE), { status: 200 }),
    ))
    render(wrap(<AskAssistant />))
    fireEvent.change(screen.getByTestId('ask-input'), { target: { value: 'What is delta?' } })
    fireEvent.click(screen.getByTestId('ask-submit'))
    expect(await screen.findByTestId('ask-answer')).toBeTruthy()
    expect(screen.getByText(/Delta measures/)).toBeTruthy()
  })

  it('shows citations with clickable buttons', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify(ANSWER_RESPONSE), { status: 200 }),
    ))
    const onSelect = vi.fn()
    render(wrap(<AskAssistant onSelectModule={onSelect} />))
    fireEvent.change(screen.getByTestId('ask-input'), { target: { value: 'What is delta?' } })
    fireEvent.click(screen.getByTestId('ask-submit'))
    await screen.findByTestId('citation-greeks')
    fireEvent.click(screen.getByTestId('citation-greeks'))
    expect(onSelect).toHaveBeenCalledWith('greeks')
  })

  it('shows upgrade nudge on 402 EntitlementError', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({ detail: { error: { code: 'ENTITLEMENT_ASK_REQUIRES_PRO' } } }),
        { status: 402 },
      ),
    ))
    render(wrap(<AskAssistant />))
    fireEvent.change(screen.getByTestId('ask-input'), { target: { value: 'anything' } })
    fireEvent.click(screen.getByTestId('ask-submit'))
    await waitFor(() => expect(screen.queryByTestId('ask-upgrade-nudge')).toBeTruthy())
    expect(screen.getByText(/The assistant is a Pro feature/)).toBeTruthy()
  })

  it('shows unavailable message on LLM_UNAVAILABLE error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({ detail: { error: { code: 'LLM_UNAVAILABLE' } } }),
        { status: 502 },
      ),
    ))
    render(wrap(<AskAssistant />))
    fireEvent.change(screen.getByTestId('ask-input'), { target: { value: 'anything' } })
    fireEvent.click(screen.getByTestId('ask-submit'))
    await waitFor(() => expect(screen.queryByTestId('ask-unavailable')).toBeTruthy())
    expect(screen.getByText(/temporarily unavailable/)).toBeTruthy()
  })

  it('shows unavailable message on FEATURE_UNAVAILABLE error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({ detail: { error: { code: 'FEATURE_UNAVAILABLE' } } }),
        { status: 503 },
      ),
    ))
    render(wrap(<AskAssistant />))
    fireEvent.change(screen.getByTestId('ask-input'), { target: { value: 'anything' } })
    fireEvent.click(screen.getByTestId('ask-submit'))
    await waitFor(() => expect(screen.queryByTestId('ask-unavailable')).toBeTruthy())
  })

  it('shows generic error on unexpected failure', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(
        JSON.stringify({ detail: { error: { code: 'INTERNAL_ERROR' } } }),
        { status: 500 },
      ),
    ))
    render(wrap(<AskAssistant />))
    fireEvent.change(screen.getByTestId('ask-input'), { target: { value: 'anything' } })
    fireEvent.click(screen.getByTestId('ask-submit'))
    await waitFor(() => expect(screen.queryByTestId('ask-error')).toBeTruthy())
  })
})


