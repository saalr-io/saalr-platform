import { NavLink } from 'react-router-dom'
import { SECTIONS } from '../app/nav'

export function Sidebar() {
  return (
    <aside className="flex flex-col overflow-auto border-r border-line bg-canvas/40 p-3">
      {SECTIONS.map((s) => (
        <div key={s.label}>
          <div className="mx-2 mb-1 mt-5 font-mono text-[9px] uppercase tracking-[2px] text-txtFaint">
            {s.label}
          </div>
          {s.items.map(([to, label]) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `group relative flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors ${
                  isActive
                    ? 'bg-panel text-txt'
                    : 'text-txtDim hover:bg-panel/60 hover:text-txt'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <span
                    className={`absolute left-0 top-1/2 h-4 -translate-y-1/2 rounded-r bg-pos transition-all ${
                      isActive ? 'w-[3px] opacity-100' : 'w-0 opacity-0'
                    }`}
                  />
                  <span
                    className={`h-1.5 w-1.5 rounded-[2px] transition-colors ${
                      isActive ? 'bg-pos' : 'bg-line group-hover:bg-txtFaint'
                    }`}
                  />
                  {label}
                </>
              )}
            </NavLink>
          ))}
        </div>
      ))}
      {import.meta.env.DEV && (
        <div>
          <div className="mx-2 mb-1 mt-5 font-mono text-[9px] uppercase tracking-[2px] text-txtFaint">Dev</div>
          <NavLink
            to="/dev"
            className={({ isActive }) =>
              `group relative flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors ${
                isActive ? 'bg-panel text-txt' : 'text-txtDim hover:bg-panel/60 hover:text-txt'
              }`
            }
          >
            Dev Seed
          </NavLink>
        </div>
      )}
      <div className="mt-auto px-2 pt-6 font-mono text-[9px] leading-relaxed text-txtFaint">
        v0.1.0 · foundation
        <br />
        scaffold + data-layer
      </div>
    </aside>
  )
}
