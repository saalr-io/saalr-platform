import { Fragment } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { breadcrumbFor } from '../app/nav'

/**
 * Renders `Home > Section > … > Page` for the current route. Ancestors link;
 * the section and current page are plain text. Renders nothing on the dashboard
 * root (empty trail).
 */
export function Breadcrumbs() {
  const { pathname } = useLocation()
  const crumbs = breadcrumbFor(pathname)
  if (crumbs.length === 0) return null

  return (
    <nav aria-label="Breadcrumb" className="mb-4 text-xs">
      <ol className="flex flex-wrap items-center gap-1.5 text-txtFaint">
        {crumbs.map((c, i) => {
          const isLast = i === crumbs.length - 1
          return (
            <Fragment key={`${c.label}-${i}`}>
              {i > 0 && <span aria-hidden="true">›</span>}
              <li>
                {c.to ? (
                  <Link to={c.to} className="text-txtDim transition-colors hover:text-txt">
                    {c.label}
                  </Link>
                ) : (
                  <span className={isLast ? 'text-txt' : undefined} aria-current={isLast ? 'page' : undefined}>
                    {c.label}
                  </span>
                )}
              </li>
            </Fragment>
          )
        })}
      </ol>
    </nav>
  )
}
