export default function Page() {
  return (
    <main className="mx-auto max-w-2xl px-6 py-20">
      <h1 className="text-3xl font-bold tracking-tight">Saalr</h1>
      <p className="mt-4 text-txtDim">
        Saalr is a research-grade options analytics terminal. Build and price
        multi-leg strategies, study payoff and volatility behaviour, and run
        screens and backtests against point-in-time market data — all from one
        fast, keyboard-driven workspace.
      </p>
      <nav className="mt-8 flex gap-4">
        <a href="/learn" className="text-accent underline">
          Learn options strategies
        </a>
        <a href="/app" className="text-accent underline">
          Go to app
        </a>
      </nav>
    </main>
  )
}
