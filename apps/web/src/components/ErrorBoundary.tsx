import { Component, type ErrorInfo, type ReactNode } from 'react'

interface State {
  error: Error | null
}

/**
 * Catches render-time exceptions anywhere below it and shows the error instead of
 * unmounting the whole tree to a blank page. Without this, any thrown error in a
 * route leaves the user staring at an empty screen with no clue what failed.
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('App crashed:', error, info.componentStack)
  }

  render() {
    const { error } = this.state
    if (error) {
      return (
        <div className="grid min-h-screen place-items-center bg-canvas p-6">
          <div className="w-full max-w-2xl space-y-3 rounded-lg border border-neg/40 bg-panel p-5" data-testid="app-error">
            <p className="font-mono text-[11px] uppercase tracking-wider text-neg">Something broke</p>
            <p className="text-sm text-txt">The app hit an unexpected error and stopped rendering.</p>
            <pre className="max-h-72 overflow-auto rounded bg-canvas p-3 font-mono text-[11px] leading-relaxed text-txtDim">
              {error.message}
              {error.stack ? `\n\n${error.stack}` : ''}
            </pre>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="rounded-md bg-accent px-4 py-2 text-xs font-medium text-canvas transition hover:opacity-90"
            >
              Reload
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
