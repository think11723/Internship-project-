import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

const STORAGE_KEY = 'fundflow:report'

const ReportContext = createContext(null)

const readStoredReport = () => {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : null
  } catch (_) {
    return null
  }
}

const writeStoredReport = (report) => {
  try {
    if (report) {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(report))
    } else {
      sessionStorage.removeItem(STORAGE_KEY)
    }
  } catch (_) {
    /* noop - sessionStorage may be full or disabled */
  }
}

export const ReportProvider = ({ children }) => {
  const [report, setReportState] = useState(() => readStoredReport())

  // Write to sessionStorage synchronously (no debounce) on every change.
  // sessionStorage writes are cheap and the report is needed immediately
  // for navigation rehydration.
  useEffect(() => {
    writeStoredReport(report)
  }, [report])

  const setReport = useCallback((next) => {
    setReportState(next || null)
  }, [])

  const clearReport = useCallback(() => {
    setReportState(null)
  }, [])

  const value = useMemo(
    () => ({ report, setReport, clearReport, hasReport: Boolean(report) }),
    [report, setReport, clearReport],
  )

  return <ReportContext.Provider value={value}>{children}</ReportContext.Provider>
}

export const useReport = () => {
  const ctx = useContext(ReportContext)
  if (!ctx) {
    throw new Error('useReport must be used within a ReportProvider')
  }
  return ctx
}
