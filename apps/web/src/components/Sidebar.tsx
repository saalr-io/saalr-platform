import { NavLink } from 'react-router-dom'

const SECTIONS: { label: string; items: [string, string][] }[] = [
  {
    label: 'Trade',
    items: [
      ['/', 'Dashboard'],
      ['/markets', 'Markets & Vol'],
      ['/strategies', 'Strategies'],
      ['/models', 'Models'],
    ],
  },
  {
    label: 'Learn & Research',
    items: [
      ['/research', 'Research Agent'],
      ['/education', 'OptionsAcademy'],
      ['/portfolio', 'Portfolio'],
    ],
  },
  { label: 'System', items: [['/system', 'System Status']] },
]

export function Sidebar() {
  return (
    <aside className="overflow-auto border-r border-line p-3">
      {SECTIONS.map((s) => (
        <div key={s.label}>
          <div className="mx-2 mb-1 mt-4 text-[9px] uppercase tracking-widest text-txtFaint">
            {s.label}
          </div>
          {s.items.map(([to, label]) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-2 rounded-lg px-3 py-2 font-medium ${
                  isActive
                    ? 'bg-panel text-txt shadow-[inset_2px_0_0] shadow-pos'
                    : 'text-txtDim hover:bg-panel hover:text-txt'
                }`
              }
            >
              {label}
            </NavLink>
          ))}
        </div>
      ))}
    </aside>
  )
}