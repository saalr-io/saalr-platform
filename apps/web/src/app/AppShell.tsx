import { Outlet } from 'react-router-dom'
import { Topbar } from '../components/Topbar'
import { Sidebar } from '../components/Sidebar'

export function AppShell() {
  return (
    <div className="grid h-screen grid-cols-[220px_1fr] grid-rows-[52px_1fr]">
      <Topbar />
      <Sidebar />
      <main className="overflow-auto p-5">
        <Outlet />
      </main>
    </div>
  )
}