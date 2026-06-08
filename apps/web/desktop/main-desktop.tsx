import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from '../src/auth/AuthContext'
import { AppRoutes } from '../src/app/Router'
import { ErrorBoundary } from '../src/components/ErrorBoundary'
import '../src/index.css'

const queryClient = new QueryClient()

// Mirrors apps/web/pages/app/+Page.tsx but with HashRouter (no /app basename)
// for the bundled desktop app.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <HashRouter>
          <AuthProvider>
            <AppRoutes />
          </AuthProvider>
        </HashRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>,
)
