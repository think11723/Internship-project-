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
          <Navbar />
          <div className="flex">
            <Sidebar />
            <main className="flex-1 ml-64 mt-16">
              <div className="max-w-7xl mx-auto px-8 py-10">
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
