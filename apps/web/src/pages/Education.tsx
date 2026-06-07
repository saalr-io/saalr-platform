import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useCompleteStep } from '../features/onboarding/hooks'
import { ModuleList } from '../features/academy/ModuleList'
import { ModuleReader } from '../features/academy/ModuleReader'
import { SearchBox } from '../features/academy/SearchBox'
import { AskAssistant } from '../features/academy/AskAssistant'
import { useModules } from '../features/academy/hooks'

export function Education() {
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null)
  const [searchParams] = useSearchParams()
  const complete = useCompleteStep()
  const readLessonFired = useRef(false)
  // Credit the onboarding `read_lesson` step only on an EXPLICIT pick (a click or a
  // ?lesson= deep-link) — never when the list merely defaults to the first lesson on
  // catalog load. Idempotent on the backend; the ref avoids duplicate fires per mount.
  function selectLesson(slug: string) {
    setSelectedSlug(slug)
    if (!readLessonFired.current) {
      readLessonFired.current = true
      complete.mutate('read_lesson')
    }
  }
  useEffect(() => {
    const lesson = searchParams.get('lesson')
    if (lesson) selectLesson(lesson)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams])
  const { data, isLoading } = useModules()

  const modules = data?.modules ?? []
  const completed = data?.completed ?? 0
  const total = data?.total ?? 0

  // Derived selection: an explicit pick wins; otherwise default to the first
  // lesson once the catalog loads (no render-phase setState).
  const activeSlug = selectedSlug ?? modules[0]?.slug ?? null
  const setActiveSlug = selectLesson

  return (
    <div className="animate-fadeUp space-y-6">
      {/* ── header ── */}
      <div className="flex flex-wrap items-baseline gap-3">
        <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-accent">
          // OptionsAcademy
        </p>
        <h2 className="text-xl font-semibold tracking-tight">Learn options trading</h2>
        {!isLoading && (
          <span
            className="ml-auto rounded border border-line bg-panel px-2 py-0.5 font-mono text-[10px] text-txtFaint"
            data-testid="progress-chip"
          >
            {completed}/{total} complete
          </span>
        )}
      </div>

      {/* ── two-pane layout ── */}
      <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
        {/* left rail: search + module list */}
        <div className="space-y-3">
          <SearchBox onSelect={setActiveSlug} />
          {isLoading ? (
            <div className="animate-pulse space-y-2 py-2">
              {[1, 2, 3, 4].map((n) => (
                <div key={n} className="h-10 rounded-lg bg-panel2" />
              ))}
            </div>
          ) : (
            <ModuleList
              modules={modules}
              activeSlug={activeSlug}
              onSelect={setActiveSlug}
            />
          )}
        </div>

        {/* right pane: reader */}
        <div className="rounded-lg border border-line bg-panel p-4">
          {activeSlug ? (
            <ModuleReader slug={activeSlug} />
          ) : (
            <div className="flex h-40 items-center justify-center text-[12px] text-txtFaint">
              Select a lesson to begin.
            </div>
          )}
        </div>
      </div>

      {/* ── ask assistant panel ── */}
      <div className="rounded-lg border border-line bg-panel p-4">
        <AskAssistant onSelectModule={setActiveSlug} />
      </div>
    </div>
  )
}
