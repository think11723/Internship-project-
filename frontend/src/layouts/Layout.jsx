import React from 'react'
import { Outlet } from 'react-router-dom'
import Navbar from '../components/Navbar'
import Sidebar from '../components/Sidebar'
import { ReportProvider } from '../context/ReportContext'
import { ResumeProvider } from '../context/ResumeContext'

const Layout = () => {
  return (
    <ReportProvider>
      <ResumeProvider>
        <div className="min-h-screen bg-background-primary">
          <a
            href="#main-content"
            className="skip-link"
          >
            Skip to main content
          </a>
          <Navbar />
          <div className="flex">
            <Sidebar />
            <main
              id="main-content"
              className="flex-1 mt-16 md:ml-64"
              tabIndex={-1}
            >
              <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 sm:py-10 lg:px-8">
                <Outlet />
              </div>
            </main>
          </div>
        </div>
      </ResumeProvider>
    </ReportProvider>
  )
}

export default Layout
