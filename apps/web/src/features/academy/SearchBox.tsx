import { useState, useEffect, useRef } from 'react'
import { useSearch } from './hooks'

interface SearchBoxProps {
  onSelect: (slug: string) => void
}

export function SearchBox({ onSelect }: SearchBoxProps) {
  const [input, setInput] = useState('')
  const [query, setQuery] = useState('')
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // debounce: 250 ms after last keystroke
  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    if (input.trim() === '') {
      setQuery('')
      return
    }
    timerRef.current = setTimeout(() => setQuery(input.trim()), 250)
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [input])

  const { data, isFetching } = useSearch(query)

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      if (timerRef.current) clearTimeout(timerRef.current)
      setQuery(input.trim())
    }
  }

  const hasResults = query.length > 0 && data && data.results.length > 0
  const noResults = query.length > 0 && data && data.results.length === 0 && !isFetching

  return (
    <div className="space-y-2">
      <div className="relative">
        <input
          type="search"
          aria-label="Search lessons"
          data-testid="search-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Search lessons…"
          className="w-full rounded-lg border border-line bg-canvas px-3 py-2 font-mono text-[12px] text-txt placeholder:text-txtFaint focus:border-accent focus:outline-none"
        />
        {isFetching && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 font-mono text-[10px] text-txtFaint">
            …
          </span>
        )}
      </div>

      {hasResults && (
        <div
          className="rounded-lg border border-line bg-panel"
          data-testid="search-results"
        >
          {data.results.map((hit) => (
            <button
              key={hit.slug}
              data-testid={`search-hit-${hit.slug}`}
              onClick={() => { setInput(''); setQuery(''); onSelect(hit.slug) }}
              className="flex w-full flex-col gap-0.5 border-b border-line px-3 py-2.5 text-left last:border-0 hover:bg-panel2"
            >
              <div className="flex items-center gap-2">
                <span className="text-[13px] font-medium text-txt">{hit.title}</span>
                {hit.locked && (
                  <span className="rounded border border-accent/30 px-1 font-mono text-[9px] uppercase tracking-[0.12em] text-accent">
                    PRO
                  </span>
                )}
              </div>
              <span className="line-clamp-1 text-[11px] text-txtFaint">{hit.snippet}</span>
            </button>
          ))}
        </div>
      )}

      {noResults && (
        <p className="px-1 text-[11px] text-txtFaint" data-testid="no-results">
          No lessons matched &ldquo;{query}&rdquo;.
        </p>
      )}
    </div>
  )
}
