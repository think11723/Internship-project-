import { Home, BarChart3, Building2, FileText } from 'lucide-react'

/**
 * The single source of truth for section navigation.
 *
 * Both the desktop sidebar (`Sidebar`) and the mobile drawer (`MobileNav`)
 * render from this list via `SidebarNav`, so the two can never drift apart.
 * Add or reorder items here and both surfaces update together.
 */
export const NAV_ITEMS = [
  { path: '/', label: 'Home', icon: Home },
  { path: '/dashboard', label: 'Dashboard', icon: BarChart3 },
  { path: '/companies', label: 'Companies', icon: Building2 },
  { path: '/resume', label: 'Resume', icon: FileText },
]

/**
 * Whether a nav item should be highlighted for the current location.
 *
 * "/" only matches exactly, otherwise it would stay highlighted on every
 * route. Every other item also matches its sub-routes, so /companies stays
 * active while viewing /companies/anthropic.
 *
 * @param {string} pathname current `location.pathname`
 * @param {string} path the nav item's path
 * @returns {boolean}
 */
export function isNavItemActive(pathname, path) {
  if (path === '/') return pathname === '/'
  return pathname === path || pathname.startsWith(path + '/')
}
