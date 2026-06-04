import { useState } from 'react'
import { Link } from 'react-router-dom'
import { EntitlementError } from '../../lib/content'
import { useAsk } from './hooks'
import { Markdown } from './markdown'

interface AskAssistantProps {
  onSelectModule?: (slug: string) => void
}

export function AskAssistant({ onSelectModule }: AskAssistantProps) {
  const [question, setQuestion] = useState('')
  const ask = useAsk()

  function submit() {
    const q = question.trim()
    if (!q) return
    ask.mutate({ question: q })
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  // classify error for display
  const isEntitlement = ask.isError && ask.error instanceof EntitlementError
  const isUnavailable =
    ask.isError &&
    !isEntitlement &&
    (ask.error.message === 'LLM_UNAVAILABLE' || ask.error.message === 'FEATURE_UNAVAILABLE')
  const isGenericError = ask.isError && !isEntitlement && !isUnavailable

  return (
    <div className="space-y-4">
      {/* kicker */}
      <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-accent">
        // Ask the assistant <span className="text-txtFaint">(Pro)</span>
      </p>

      {/* input row */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
        <textarea
          data-testid="ask-input"
          rows={2}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything about options… (Enter to send)"
          className="flex-1 resize-none rounded-lg border border-line bg-canvas px-3 py-2 font-mono text-[12px] text-txt placeholder:text-txtFaint focus:border-accent focus:outline-none"
        />
        <button
          data-testid="ask-submit"
          disabled={ask.isPending || question.trim().length === 0}
          onClick={submit}
          className="shrink-0 rounded-lg bg-accent/20 px-4 py-2 text-xs text-accent transition hover:bg-accent/30 disabled:opacity-40"
        >
          {ask.isPending ? 'Thinking…' : 'Ask'}
        </button>
      </div>

      {/* entitlement nudge */}
      {isEntitlement && (
        <div
          className="rounded-lg border border-accent/30 bg-accent/5 px-4 py-4 text-center"
          data-testid="ask-upgrade-nudge"
        >
          <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-accent">
            // Pro feature
          </p>
          <p className="mt-2 text-sm text-txtDim">
            The assistant is a Pro feature. Upgrade to unlock grounded Q&amp;A across all lessons.
          </p>
          <Link
            to="/billing?plan=pro"
            data-testid="ask-upgrade-link"
            className="mt-4 inline-block rounded-md bg-accent px-4 py-2 text-xs font-medium text-canvas transition hover:opacity-90"
          >
            Upgrade to Pro
          </Link>
        </div>
      )}

      {/* unavailable */}
      {isUnavailable && (
        <div
          className="rounded-lg border border-warn/30 bg-warn/10 px-4 py-3 text-xs text-warn"
          data-testid="ask-unavailable"
        >
          The assistant is temporarily unavailable — please try again shortly.
        </div>
      )}

      {/* generic error */}
      {isGenericError && (
        <div
          className="rounded-lg border border-neg/30 bg-neg/10 px-4 py-3 text-xs text-neg"
          data-testid="ask-error"
        >
          Something went wrong: {ask.error.message}
        </div>
      )}

      {/* answer */}
      {ask.isSuccess && ask.data && (
        <div className="space-y-4" data-testid="ask-answer">
          <div className="rounded-lg border border-line bg-panel p-4">
            <Markdown source={ask.data.answer} />
          </div>

          {ask.data.citations.length > 0 && (
            <div className="space-y-1">
              <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-txtFaint">
                Sources
              </p>
              <div className="flex flex-wrap gap-2">
                {ask.data.citations.map((c) => (
                  <button
                    key={c.slug}
                    data-testid={`citation-${c.slug}`}
                    onClick={() => onSelectModule?.(c.slug)}
                    className="rounded border border-line bg-panel2 px-2 py-1 text-[11px] text-txtDim transition hover:border-accent hover:text-accent"
                  >
                    {c.title}
                  </button>
                ))}
              </div>
              <p className="font-mono text-[9px] text-txtFaint">
                via {ask.data.model} · {ask.data.usage.prompt_tokens + ask.data.usage.completion_tokens} tokens
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
