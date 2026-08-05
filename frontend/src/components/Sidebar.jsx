import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Home, BarChart3, Building2, FileText, Sparkles } from 'lucide-react'

const Sidebar = () => {
  const location = useLocation()

  const navItems = [
    { path: '/', label: 'Home', icon: Home },
    { path: '/dashboard', label: 'Dashboard', icon: BarChart3 },
    { path: '/companies', label: 'Companies', icon: Building2 },
    { path: '/resume', label: 'Resume', icon: FileText },
  ]

  return (
    <aside className="fixed left-0 top-16 bottom-0 w-64 bg-background-secondary/40 backdrop-blur-sm border-r border-border-light">
      <nav className="p-5 space-y-1.5">
        <div className="mb-6">
          <div className="flex items-center gap-2 px-3 py-2.5 rounded-pipeup bg-accent-lime/10 border-2 border-accent-lime/30">
            <Sparkles className="w-3.5 h-3.5 text-primary-700" aria-hidden="true" />
            <span className="text-[10px] font-bold uppercase tracking-wider text-primary-700">AI Powered</span>
          </div>
        </div>
        {navItems.map((item) => {
          const Icon = item.icon
          const isActive = location.pathname === item.path
          return (
            <Link
              key={item.path}
              to={item.path}
              aria-current={isActive ? 'page' : undefined}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-pipeup transition-all duration-pipeup ${
                isActive
                  ? 'bg-accent-lime text-dark-primary shadow-pipeup font-bold'
                  : 'text-gray-800 font-semibold hover:text-dark-primary hover:bg-background-card hover:shadow-pipeup'
              }`}
            >
              <Icon className={`w-4 h-4 ${isActive ? 'text-dark-primary' : 'text-gray-700'}`} aria-hidden="true" />
              <span className="text-sm">{item.label}</span>
            </Link>
          )
        })}
      </nav>
    </aside>
  )
}

export default Sidebar
