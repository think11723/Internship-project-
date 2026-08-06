import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Home, BarChart3, Building2, FileText } from 'lucide-react'

const Sidebar = () => {
  const location = useLocation()

  const navItems = [
    { path: '/', label: 'Home', icon: Home },
    { path: '/dashboard', label: 'Dashboard', icon: BarChart3 },
    { path: '/companies', label: 'Companies', icon: Building2 },
    { path: '/resume', label: 'Resume', icon: FileText },
  ]

  return (
    <aside
      className="fixed left-0 top-16 bottom-0 w-64 bg-background-secondary/40 backdrop-blur-sm border-r border-border-light hidden md:block"
      aria-label="Section navigation"
    >
      <nav className="p-5 space-y-1.5">
        {navItems.map((item) => {
          const Icon = item.icon
          const isActive =
            item.path === '/'
              ? location.pathname === '/'
              : location.pathname === item.path ||
                location.pathname.startsWith(item.path + '/')
          return (
            <Link
              key={item.path}
              to={item.path}
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
    </aside>
  )
}

export default Sidebar
