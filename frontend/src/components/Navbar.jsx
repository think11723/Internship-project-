import React from 'react'
import { Link } from 'react-router-dom'

const Navbar = () => {
  return (
    <nav className="fixed top-0 left-0 right-0 h-16 z-50" aria-label="Primary">
      <div className="absolute inset-0 backdrop-blur-md bg-background-card/90 border-b border-border-light" />
      <div className="relative flex items-center justify-between h-full px-8 max-w-7xl mx-auto">
        <Link to="/" className="flex items-center gap-3 group" aria-label="FundFlow AI home">
          <div className="w-10 h-10 bg-accent-lime rounded-pipeup flex items-center justify-center shadow-pipeup group-hover:shadow-pipeup-lg transition-all duration-pipeup group-hover:scale-105">
            <span className="text-dark-primary font-bold text-xl font-sans" aria-hidden="true">F</span>
          </div>
          <div className="flex flex-col">
            <span className="text-lg font-bold text-dark-primary font-sans tracking-tight">FundFlow AI</span>
            <span className="text-[10px] font-semibold text-gray-700 tracking-wide">Autonomous Career Intelligence</span>
          </div>
        </Link>
        <div className="flex items-center gap-5">
          <Link
            to="/dashboard"
            className="text-xs font-bold text-gray-700 hover:text-dark-primary transition-colors duration-pipeup"
          >
            Dashboard
          </Link>
          <Link
            to="/companies"
            className="text-xs font-bold text-gray-700 hover:text-dark-primary transition-colors duration-pipeup"
          >
            Companies
          </Link>
          <Link
            to="/resume"
            className="px-5 py-2.5 text-xs font-bold bg-accent-lime text-dark-primary rounded-pipeup shadow-pipeup hover:bg-accent-limeHover hover:shadow-pipeup-lg hover:-translate-y-0.5 transition-all duration-pipeup"
          >
            Upload Resume
          </Link>
        </div>
      </div>
    </nav>
  )
}

export default Navbar

