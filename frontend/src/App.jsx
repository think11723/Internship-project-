import React from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Layout from './layouts/Layout'
import Landing from './pages/Landing'
import Dashboard from './pages/Dashboard'
import ResumeUpload from './pages/ResumeUpload'
import CompanyDetails from './pages/CompanyDetails'
import Companies from './pages/Companies'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Landing />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="companies" element={<Companies />} />
          <Route path="resume" element={<ResumeUpload />} />
          <Route path="company/:companyName" element={<CompanyDetails />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
