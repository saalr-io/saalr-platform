import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from '../../src/auth/AuthContext'
import { AppRoutes } from '../../src/app/Router'
import { ErrorBoundary } from '../../src/components/ErrorBoundary'

const queryClient = new QueryClient()

// Client-only (ssr: false) mount of the authenticated SPA. basename="/app"
// makes the relative routes in <AppRoutes/> resolve to /app, /app/markets, etc.
export default function Page() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter basename="/app">
          <AuthProvider>
            <AppRoutes />
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  )
}
