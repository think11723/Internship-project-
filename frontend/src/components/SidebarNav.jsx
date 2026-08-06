import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import { NAV_ITEMS, isNavItemActive } from './navItems'

/**
 * The section-navigation link list.
 *
 * Rendered by BOTH the desktop sidebar and the mobile drawer so the items,
 * icons, active highlighting and routing behaviour are identical on every
 * breakpoint — there is no second copy of this markup to keep in sync.
 *
 * @param {object}   props
 * @param {Function} [props.onNavigate] called when a link is activated.
 *   The drawer passes its close handler so navigation dismisses it. Fires on
 *   every click, including a link to the current route (where `location`
 *   would not change and an effect alone would not fire).
 */
const SidebarNav = ({ onNavigate }) => {
  const location = useLocation()

  return (
    <nav className="p-5 space-y-1.5">
      {NAV_ITEMS.map((item) => {
        const Icon = item.icon
        const isActive = isNavItemActive(location.pathname, item.path)
        return (
          <Link
            key={item.path}
            to={item.path}
            onClick={onNavigate}
            aria-current={isActive ? 'page' : undefined}
            className={`group flex items-center gap-3 px-3 py-2.5 rounded-pipeup transition-all duration-pipeup ${
              isActive
                ? 'bg-accent-lime text-dark-primary shadow-pipeup font-bold'
                : 'text-gray-800 font-semibold hover:text-dark-primary hover:bg-background-card hover:shadow-pipeup'
            }`}
          >
            <Icon
              className={`w-4 h-4 transition-transform duration-pipeup group-hover:scale-110 ${
                isActive ? 'text-dark-primary' : 'text-gray-700'
              }`}
              aria-hidden="true"
            />
            <span className="text-sm">{item.label}</span>
          </Link>
        )
      })}
    </nav>
  )
}

export default SidebarNav
