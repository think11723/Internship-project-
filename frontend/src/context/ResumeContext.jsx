import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'

import { getResumeLatest } from '../services/resumeService'

const ResumeContext = createContext(null)

export const ResumeProvider = ({ children }) => {
  const [currentResume, setCurrentResumeState] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await getResumeLatest()
      setCurrentResumeState(response.data || null)
    } catch (err) {
      // 404 means no resume yet — leave currentResume null
      if (err.response?.status === 404) {
        setCurrentResumeState(null)
      } else {
        setError(err.response?.data?.detail || 'Failed to load resume metadata')
        setCurrentResumeState(null)
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const setCurrentResume = useCallback((next) => {
    setCurrentResumeState(next || null)
  }, [])

  const clearResume = useCallback(() => {
    setCurrentResumeState(null)
  }, [])

  const value = useMemo(
    () => ({
      currentResume,
      setCurrentResume,
      clearResume,
      refreshResume: refresh,
      loading,
      error,
    }),
    [currentResume, setCurrentResume, clearResume, refresh, loading, error],
  )

  return <ResumeContext.Provider value={value}>{children}</ResumeContext.Provider>
}

export const useResume = () => {
  const ctx = useContext(ResumeContext)
  if (!ctx) {
    throw new Error('useResume must be used within a ResumeProvider')
  }
  return ctx
}
