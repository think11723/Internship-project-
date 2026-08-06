import React from 'react'
import { Link, NavLink } from 'react-router-dom'
import Brand from './Brand'
import MobileNav from './MobileNav'

const Navbar = () => {
  return (
    <nav
      className="fixed top-0 left-0 right-0 h-16 z-50"
      aria-label="Primary"
    >
      <div className="absolute inset-0 backdrop-blur-md bg-background-card/90 border-b border-border-light" />
      <div className="relative flex items-center justify-between h-full px-6 sm:px-8 max-w-7xl mx-auto">
        <div className="flex items-center">
          {/* Hamburger trigger plus the drawer it controls. Both are
              hidden at md and above, where the desktop sidebar takes over,
              so this adds nothing to the desktop layout. */}
          <MobileNav />
          <Brand />
        </div>
        <div className="flex items-center gap-3 sm:gap-5">
          <NavLink
            to="/dashboard"
            className={({ isActive }) =>
              [
                'hidden sm:inline-block text-xs font-bold transition-colors duration-pipeup',
                isActive
                  ? 'text-dark-primary'
                  : 'text-gray-700 hover:text-dark-primary',
              ].join(' ')
            }
          >
            Dashboard
          </NavLink>
          <NavLink
            to="/companies"
            className={({ isActive }) =>
              [
                'hidden sm:inline-block text-xs font-bold transition-colors duration-pipeup',
                isActive
                  ? 'text-dark-primary'
                  : 'text-gray-700 hover:text-dark-primary',
              ].join(' ')
            }
          >
            Companies
          </NavLink>
          <Link
            to="/resume"
            className="px-4 sm:px-5 py-2 sm:py-2.5 text-xs font-bold bg-accent-lime text-dark-primary rounded-pipeup shadow-pipeup hover:bg-accent-limeHover hover:shadow-pipeup-lg hover:-translate-y-0.5 transition-all duration-pipeup"
          >
            Upload Resume
          </Link>
        </div>
      </div>
    </nav>
  )
}

export default Navbar

