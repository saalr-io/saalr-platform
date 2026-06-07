import { Routes, Route, Navigate } from 'react-router-dom'
import { RequireAuth } from '../components/RequireAuth'
import { AppShell } from './AppShell'
import { SystemStatus } from '../pages/SystemStatus'
import { Strategies } from '../pages/Strategies'
import { Education } from '../pages/Education'
import { Research } from '../pages/Research'
import { Login } from '../pages/Login'
import { VerifyMagicLink } from '../pages/VerifyMagicLink'
import { Billing } from '../pages/Billing'
import { BillingSuccess } from '../pages/BillingSuccess'
import { BillingCancel } from '../pages/BillingCancel'
import { Markets } from '../pages/Markets'
import { Portfolio } from '../pages/Portfolio'
import { Models } from '../pages/Models'
import { Dashboard } from '../pages/Dashboard'
import { Backtests } from '../pages/Backtests'
import { Ideas } from '../pages/Ideas'
import { Start } from '../pages/Start'

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
        <Route index element={<Dashboard />} />
        <Route path="markets" element={<Markets />} />
        <Route path="strategies" element={<Strategies />} />
        <Route path="ideas" element={<Ideas />} />
        <Route path="backtests" element={<Backtests />} />
        <Route path="models" element={<Models />} />
        <Route path="research" element={<Research />} />
        <Route path="education" element={<Education />} />
        <Route path="billing" element={<Billing />} />
        <Route path="billing/success" element={<BillingSuccess />} />
        <Route path="billing/cancel" element={<BillingCancel />} />
        <Route path="portfolio" element={<Portfolio />} />
        <Route path="start" element={<Start />} />
        <Route path="system" element={<SystemStatus />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
