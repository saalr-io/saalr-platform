import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppShell } from './app/AppShell'
import { SystemStatus } from './pages/SystemStatus'
import { PlaceholderPage } from './components/PlaceholderPage'
import './index.css'

const queryClient = new QueryClient()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<PlaceholderPage title="Dashboard" />} />
            <Route path="markets" element={<PlaceholderPage title="Markets & Vol" />} />
            <Route path="strategies" element={<PlaceholderPage title="Strategies" />} />
            <Route path="models" element={<PlaceholderPage title="Models" />} />
            <Route path="research" element={<PlaceholderPage title="Research Agent" />} />
            <Route path="education" element={<PlaceholderPage title="OptionsAcademy" />} />
            <Route path="portfolio" element={<PlaceholderPage title="Portfolio" />} />
            <Route path="system" element={<SystemStatus />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
)