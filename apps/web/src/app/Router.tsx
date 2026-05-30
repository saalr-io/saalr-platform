import { Routes, Route, Navigate } from 'react-router-dom'
import { RequireAuth } from '../components/RequireAuth'
import { AppShell } from './AppShell'
import { SystemStatus } from '../pages/SystemStatus'
import { PlaceholderPage } from '../components/PlaceholderPage'
import { Strategies } from '../pages/Strategies'
import { Login } from '../pages/Login'
import { VerifyMagicLink } from '../pages/VerifyMagicLink'

/**
 * The authenticated SPA route table. Mounted under a <BrowserRouter basename="/app">
 * so the relative paths below resolve to /app, /app/markets, /app/strategies, etc.
 */
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/auth/verify" element={<VerifyMagicLink />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<PlaceholderPage title="Dashboard" />} />
        <Route path="markets" element={<PlaceholderPage title="Markets & Vol" />} />
        <Route path="strategies" element={<Strategies />} />
        <Route path="models" element={<PlaceholderPage title="Models" />} />
        <Route path="research" element={<PlaceholderPage title="Research Agent" />} />
        <Route path="education" element={<PlaceholderPage title="OptionsAcademy" />} />
        <Route path="portfolio" element={<PlaceholderPage title="Portfolio" />} />
        <Route path="system" element={<SystemStatus />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
