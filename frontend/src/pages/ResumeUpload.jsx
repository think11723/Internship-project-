import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Link } from 'react-router-dom'
import { Award, Calendar, CheckCircle2, Sparkles, Target } from 'lucide-react'
import Card from '../components/Card'
import Button from '../components/Button'
import Loader from '../components/Loader'
import {
  uploadResume,
  deleteResumeLatest,
  getResumeLatestAnalysis,
  getUploadStatus,
} from '../services/resumeService'
import { getCompanies } from '../services/companyService'
import { getCareerPlan } from '../services/careerService'
import { useResume } from '../context/ResumeContext'
import { useReport } from '../context/ReportContext'

// The 9 user-facing stages. `key` is the value the backend emits
// (or, for the "Uploading" stage, the value the client itself emits
// from the axios onUploadProgress callback).
const UPLOAD_STAGES = [
  { key: 'Uploading Resume', label: 'Uploading Resume', client: true },
  { key: 'Reading PDF', label: 'Reading PDF' },
  { key: 'Extracting Text', label: 'Extracting Text' },
  { key: 'Understanding Skills', label: 'Understanding Skills' },
  { key: 'Understanding Experience', label: 'Understanding Experience' },
  { key: 'Finding Technologies', label: 'Finding Technologies' },
  { key: 'Generating Career Profile', label: 'Generating Career Profile' },
  { key: 'Finalizing Analysis', label: 'Finalizing Analysis' },
  { key: 'Completed', label: 'Completed' },
]

const POLL_INTERVAL_MS = 1500
const PROGRESS_TICK_MS = 900

const formatBytes = (bytes) => {
  if (bytes == null) return null
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

const formatDate = (iso) => {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString('en-US', {
      dateStyle: 'medium',
      timeStyle: 'short',
    })
  } catch {
    return iso
  }
}

const StageProgress = ({ currentStage, percent }) => {
  const currentIndex = UPLOAD_STAGES.findIndex((s) => s.key === currentStage)
  const safeIndex = currentIndex < 0 ? 0 : currentIndex
  const total = UPLOAD_STAGES.length
  const barPercent = Math.min(
    Math.max(((safeIndex + Math.max(percent, 0) / 100)) / total * 100, safeIndex > 0 ? (safeIndex / total) * 100 : 0),
    100,
  )

  return (
    <div className="space-y-3.5">
      <div className="flex items-center gap-2.5">
        <Loader size="small" />
        <div className="flex-1">
          <p className="text-sm font-bold text-dark-primary">
            {currentStage ? `Stage: ${currentStage}` : 'Starting…'}
          </p>
          <p className="mt-0.5 text-xs font-semibold text-gray-700">
            {percent != null && currentStage !== 'Completed'
              ? `~${Math.round(percent)}% of current stage`
              : currentStage === 'Completed'
                ? 'Done'
                : 'Please wait — AI is reading your resume'}
          </p>
        </div>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-background-secondary">
        <div
          className="h-full bg-gradient-to-r from-primary-500 to-accent-lime transition-all duration-500"
          style={{ width: `${barPercent}%` }}
        />
      </div>
      <ul className="space-y-2">
        {UPLOAD_STAGES.map((s, i) => {
          const state = i < safeIndex ? 'completed' : i === safeIndex ? 'current' : 'pending'
          return (
            <li
              key={s.key}
              className={`flex items-center gap-2.5 text-xs font-semibold ${
                state === 'completed'
                  ? 'text-primary-700'
                  : state === 'current'
                    ? 'text-dark-primary'
                    : 'text-gray-700'
              }`}
            >
              {state === 'completed' ? (
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-accent-lime/30 border border-accent-lime/50">
                  <svg className="h-2.5 w-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                </span>
              ) : state === 'current' ? (
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-accent-lime/40 border border-accent-lime/50">
                  <span className="h-2.5 w-2.5 animate-spin rounded-full border-2 border-accent-lime border-t-transparent" />
                </span>
              ) : (
                <span className="flex h-5 w-5 items-center justify-center rounded-full border border-border-medium bg-background-secondary">
                  <span className="h-1.5 w-1.5 rounded-full bg-muted-medium" />
                </span>
              )}
              <span>{s.label}</span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

const CurrentResumeCard = ({
  currentResume,
  onView,
  onReplace,
  onDelete,
  deleting,
  replacing,
  viewLoading,
}) => {
  if (!currentResume) return null
  return (
    <Card>
      <div className="space-y-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-pipeup bg-accent-lime/10 border border-accent-lime/30">
              <span className="text-xl">📄</span>
            </div>
            <div className="min-w-0">
              <p className="text-sm font-bold text-dark-primary">
                Current Resume
              </p>
              <p className="mt-0.5 truncate text-xs font-semibold text-gray-700">
                {currentResume.original_filename || 'resume.pdf'}
              </p>
            </div>
          </div>
          <span className="rounded-full border border-accent-lime/40 bg-accent-lime/10 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-primary-700">
            {currentResume.status === 'analyzed' ? 'Analysis ready' : currentResume.status}
          </span>
        </div>

        <div className="grid gap-2.5 text-xs sm:grid-cols-2">
          {currentResume.name && (
            <div>
              <span className="font-semibold text-gray-700">Candidate:</span>{' '}
              <span className="font-bold text-dark-primary">{currentResume.name}</span>
            </div>
          )}
          {currentResume.skills_count != null && (
            <div>
              <span className="font-semibold text-gray-700">Skills detected:</span>{' '}
              <span className="font-bold text-dark-primary">{currentResume.skills_count}</span>
            </div>
          )}
          {currentResume.file_size != null && (
            <div>
              <span className="font-semibold text-gray-700">Size:</span>{' '}
              <span className="font-bold text-dark-primary">{formatBytes(currentResume.file_size)}</span>
            </div>
          )}
          {currentResume.parsed_at && (
            <div>
              <span className="font-semibold text-gray-700">Uploaded:</span>{' '}
              <span className="font-bold text-dark-primary">{formatDate(currentResume.parsed_at)}</span>
            </div>
          )}
        </div>

        {currentResume.summary && (
          <p className="rounded-pipeup border border-border-medium bg-background-secondary p-3.5 text-sm font-medium leading-6 text-dark-primary">
            {currentResume.summary.length > 280
              ? `${currentResume.summary.slice(0, 280)}…`
              : currentResume.summary}
          </p>
        )}

        <div className="flex flex-wrap gap-2">
          <Button
            size="small"
            variant="secondary"
            onClick={onView}
            disabled={viewLoading}
          >
            {viewLoading ? 'Loading…' : 'View Resume'}
          </Button>
          <Button
            size="small"
            variant="secondary"
            onClick={onReplace}
            disabled={replacing || deleting}
          >
            {replacing ? 'Preparing…' : 'Replace Resume'}
          </Button>
          <Button
            size="small"
            variant="ghost"
            onClick={onDelete}
            disabled={replacing || deleting}
          >
            {deleting ? 'Deleting…' : 'Delete Resume'}
          </Button>
        </div>
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Sprint 14.3 — Career Improvement Roadmap.
//
// Fetches the companies list and aggregates the per-company
// ``recommendation.{resume_improvements, interview_prep}`` blocks
// across the portfolio into a Week 1 / Week 2 / Week 3 timeline.
// All data comes from the existing recommendation engine — no
// new endpoints, no new APIs.
// ---------------------------------------------------------------------------

const CareerImprovementRoadmap = () => {
  const [companies, setCompanies] = useState([])
  // Sprint 14.4 — Portfolio progress strip from /api/career-plan.
  const [planner, setPlanner] = useState(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let cancelled = false
    Promise.all([
      getCompanies({ limit: 200 }).catch(() => ({ data: { companies: [] } })),
      getCareerPlan().catch(() => null),
    ])
      .then(([listRes, careerPlan]) => {
        if (cancelled) return
        setCompanies(listRes.data?.companies || [])
        setPlanner(
          careerPlan && !careerPlan.requires_resume ? careerPlan : null,
        )
      })
      .finally(() => {
        if (cancelled) return
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Aggregate missing keywords + ats improvements + bullet coaching
  // + interview topics across the portfolio. Deduplicate.
  const missingKeywordsSet = new Set()
  const atsSet = new Set()
  const bulletSet = new Set()
  const topicSet = new Set()
  const weaknessSet = new Set()
  for (const c of companies) {
    const rec = c?.recommendation || {}
    const ri = rec.resume_improvements || {}
    for (const k of ri.missing_keywords || []) {
      if (k) missingKeywordsSet.add(k)
    }
    for (const k of ri.ats_improvements || []) {
      if (k) atsSet.add(k)
    }
    for (const k of ri.suggested_bullet_improvements || []) {
      if (k) bulletSet.add(k)
    }
    for (const k of ri.weaknesses || []) {
      if (k) weaknessSet.add(k)
    }
    const ip = rec.interview_prep || {}
    for (const k of ip.likely_topics || []) {
      if (k) topicSet.add(k)
    }
  }
  const missingKeywords = [...missingKeywordsSet].slice(0, 6)
  const ats = [...atsSet].slice(0, 4)
  const bullets = [...bulletSet].slice(0, 4)
  const topics = [...topicSet].slice(0, 6)
  const weaknesses = [...weaknessSet].slice(0, 3)

  if (loading) {
    return (
      <Card>
        <div className="space-y-3" aria-hidden="true">
          <div className="flex items-center gap-2">
            <Calendar className="h-4 w-4 text-primary-700" aria-hidden="true" />
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
              Career Improvement Roadmap
            </p>
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            <div className="h-32 animate-pulse rounded-pipeup bg-background-secondary" />
            <div className="h-32 animate-pulse rounded-pipeup bg-background-secondary" />
            <div className="h-32 animate-pulse rounded-pipeup bg-background-secondary" />
          </div>
        </div>
      </Card>
    )
  }

  const hasContent =
    missingKeywords.length > 0 ||
    ats.length > 0 ||
    bullets.length > 0 ||
    topics.length > 0 ||
    weaknesses.length > 0 ||
    planner != null
  if (!hasContent) {
    return (
      <Card>
        <div className="empty-state">
          <span
            aria-hidden="true"
            className="inline-flex h-14 w-14 items-center justify-center rounded-full bg-accent-lime/15 text-primary-700 shadow-pipeup"
          >
            <Calendar className="h-7 w-7" aria-hidden="true" />
          </span>
          <h3 className="text-lg font-bold text-dark-primary">
            Generate your weekly report to see a personalised roadmap.
          </h3>
          <p className="max-w-md text-sm text-gray-700">
            The roadmap aggregates coaching notes from every active
            opportunity and tells you what to improve first.
          </p>
          <Link to="/dashboard">
            <Button size="small">Open Dashboard</Button>
          </Link>
        </div>
      </Card>
    )
  }

  return (
    <Card className="border-primary-500/30">
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Calendar className="h-4 w-4 text-primary-700" aria-hidden="true" />
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
            Career Improvement Roadmap
          </p>
        </div>

        {/* Sprint 14.4 — Portfolio progress strip from
            /api/career-plan. Sits between the section header and
            the Week columns so the user reads "where do I stand"
            before "what do I improve". */}
        {planner && <PortfolioProgressStrip planner={planner} />}

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <RoadmapColumn
            label="Week 1"
            title="Resume bullets"
            icon={Sparkles}
            iconClass="text-amber-700"
            items={bullets}
          />
          <RoadmapColumn
            label="Week 2"
            title="Priority skills"
            icon={Target}
            iconClass="text-primary-700"
            items={missingKeywords.map((k) => `Add "${k}" to your skills section`)}
          />
          <RoadmapColumn
            label="Week 3"
            title="Interview topics"
            icon={Award}
            iconClass="text-emerald-600"
            items={topics}
          />
        </div>

        {(weaknesses.length > 0 || ats.length > 0) && (
          <div className="border-t border-border-medium pt-3">
            <p className="text-[10px] font-bold uppercase tracking-widest text-gray-700">
              Resume weaknesses to address
            </p>
            <ul className="mt-2 space-y-1.5">
              {[...weaknesses, ...ats].slice(0, 6).map((w, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2 text-xs font-medium leading-5 text-dark-primary"
                >
                  <span
                    aria-hidden="true"
                    className="mt-0.5 inline-flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-full bg-red-500/20 text-red-700"
                  >
                    <svg className="h-2.5 w-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3} aria-hidden="true">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01M5.07 19h13.86a2 2 0 001.74-3L13.74 4a2 2 0 00-3.48 0L3.34 16a2 2 0 001.73 3z" />
                    </svg>
                  </span>
                  <span>{w}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  )
}

// Sprint 14.4 — Portfolio progress strip rendered above the Week
// columns on the Resume page. Surfaces the weekly goal, estimated
// hours, and the high/medium/long/total portfolio counts from
// /api/career-plan.
const PortfolioProgressStrip = ({ planner }) => {
  const portfolio = planner?.portfolio || {}
  const counts = [
    {
      label: 'High priority',
      value: portfolio.high_priority_count || 0,
      tone:
        'border-emerald-500/40 bg-emerald-500/10 text-emerald-700',
    },
    {
      label: 'Medium',
      value: portfolio.medium_priority_count || 0,
      tone: 'border-primary-500/40 bg-primary-500/10 text-primary-700',
    },
    {
      label: 'Long term',
      value: portfolio.long_term_count || 0,
      tone: 'border-amber-500/40 bg-amber-500/10 text-amber-800',
    },
    {
      label: 'Total',
      value: portfolio.total_companies || 0,
      tone:
        'border-border-medium bg-background-secondary text-gray-800',
    },
  ]
  return (
    <div className="space-y-2 rounded-pipeup border border-border-light bg-background-secondary p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[10px] font-bold uppercase tracking-widest text-gray-700">
          Portfolio progress
        </p>
        {typeof planner?.estimated_hours_required === 'number' &&
          planner.estimated_hours_required > 0 && (
            <span className="rounded-full border border-primary-500/40 bg-primary-500/10 px-2.5 py-0.5 text-[10px] font-bold text-primary-700">
              ~{planner.estimated_hours_required}h this week
            </span>
          )}
      </div>
      {planner?.weekly_goal && (
        <p className="text-xs font-medium leading-5 text-dark-primary">
          <span className="font-semibold">Weekly goal:</span>{' '}
          {planner.weekly_goal}
        </p>
      )}
      <div className="grid grid-cols-4 gap-2">
        {counts.map((c) => (
          <div
            key={c.label}
            className={`rounded-pipeup border px-2.5 py-1.5 text-center ${c.tone}`}
            title={c.label}
          >
            <p className="text-[9px] font-bold uppercase tracking-widest opacity-80">
              {c.label}
            </p>
            <p className="mt-0.5 text-lg font-bold leading-none">{c.value}</p>
          </div>
        ))}
      </div>
      {portfolio.text && (
        <p className="text-[11px] font-medium leading-5 text-gray-700">
          {portfolio.text}
        </p>
      )}
    </div>
  )
}

const RoadmapColumn = ({ label, title, icon: Icon, iconClass, items }) => {
  if (!items || items.length === 0) {
    return (
      <div className="rounded-pipeup border border-border-light bg-background-secondary p-3.5">
        <div className="flex items-center gap-2">
          <Icon className={`h-4 w-4 ${iconClass}`} aria-hidden="true" />
          <p className="text-[10px] font-bold uppercase tracking-widest text-gray-700">
            {label}
          </p>
        </div>
        <p className="mt-2 text-sm font-bold text-dark-primary">{title}</p>
        <p className="mt-1.5 text-xs font-medium leading-5 text-gray-700">
          No suggestions yet — generate the weekly report to populate.
        </p>
      </div>
    )
  }
  return (
    <div className="rounded-pipeup border border-border-light bg-background-secondary p-3.5">
      <div className="flex items-center gap-2">
        <Icon className={`h-4 w-4 ${iconClass}`} aria-hidden="true" />
        <p className="text-[10px] font-bold uppercase tracking-widest text-gray-700">
          {label}
        </p>
      </div>
      <p className="mt-1.5 text-sm font-bold text-dark-primary">{title}</p>
      <ul className="mt-2 space-y-1.5">
        {items.slice(0, 5).map((item, i) => (
          <li
            key={i}
            className="flex items-start gap-2 text-xs font-medium leading-5 text-dark-primary"
          >
            <span
              aria-hidden="true"
              className="mt-0.5 inline-flex h-4 w-4 flex-shrink-0 items-center justify-center rounded border-2 border-primary-500/40 bg-background-card text-[9px] font-bold text-primary-700"
            >
              {i + 1}
            </span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

const ResumeUpload = () => {
  const navigate = useNavigate()
  const { currentResume, refreshResume } = useResume()
  const { clearReport } = useReport()

  const [file, setFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [currentStage, setCurrentStage] = useState(null)
  const [stagePercent, setStagePercent] = useState(0)
  const [error, setError] = useState(null)
  const [analysis, setAnalysis] = useState(null)
  const [successMessage, setSuccessMessage] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [confirmReplace, setConfirmReplace] = useState(false)
  const [replacing, setReplacing] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [viewLoading, setViewLoading] = useState(false)
  const [viewingResume, setViewingResume] = useState(null)

  const fileInputRef = useRef(null)
  const jobIdRef = useRef(null)
  const pollIntervalRef = useRef(null)
  const stageTickRef = useRef(null)
  const uploadedBytesRef = useRef(0)
  const totalBytesRef = useRef(0)
  const lastStageKeyRef = useRef(null)
  const navigationLockRef = useRef(false)

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
      if (stageTickRef.current) clearInterval(stageTickRef.current)
    }
  }, [])

  const handleFileSelect = (selectedFile) => {
    const isPdf =
      selectedFile &&
      (selectedFile.type === 'application/pdf' ||
        selectedFile.name?.toLowerCase().endsWith('.pdf'))
    if (isPdf) {
      setFile(selectedFile)
      setError(null)
      setSuccessMessage('')
      setConfirmReplace(false)
    } else {
      setError('Please select a PDF file')
    }
  }

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    const droppedFile = e.dataTransfer.files[0]
    handleFileSelect(droppedFile)
  }, [])

  const handleDragOver = (e) => {
    e.preventDefault()
  }

  const stopPolling = () => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current)
      pollIntervalRef.current = null
    }
    if (stageTickRef.current) {
      clearInterval(stageTickRef.current)
      stageTickRef.current = null
    }
  }

  const applyStage = (stageKey) => {
    if (!stageKey) return
    if (lastStageKeyRef.current === stageKey) return
    lastStageKeyRef.current = stageKey
    setCurrentStage(stageKey)
    setStagePercent(0)

    if (stageTickRef.current) clearInterval(stageTickRef.current)
    // Only animate stage-internal progress while the network upload is
    // *not* the active stage (the axios onUploadProgress handles that).
    if (stageKey !== 'Uploading Resume') {
      stageTickRef.current = setInterval(() => {
        setStagePercent((p) => (p >= 90 ? 95 : p + 8))
      }, PROGRESS_TICK_MS)
    }
  }

  const startPolling = (jobId) => {
    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
    pollIntervalRef.current = setInterval(async () => {
      try {
        const response = await getUploadStatus(jobId)
        const data = response.data || {}
        if (data.stage) applyStage(data.stage)
        if (data.status === 'done') {
          stopPolling()
          setCurrentStage('Completed')
          setStagePercent(100)
          handleUploadSuccess(data.result || null)
        } else if (data.status === 'failed') {
          stopPolling()
          setUploading(false)
          setError(
            (data.error && `Upload failed: ${data.error}`) ||
              'Resume analysis failed. Please try again.',
          )
        }
      } catch (err) {
        // 404 / network blip — keep polling
      }
    }, POLL_INTERVAL_MS)
  }

  const handleUploadSuccess = async (result) => {
    setUploading(false)
    setSuccessMessage('Resume analyzed successfully. Ready to use.')
    if (result && result.profile) {
      setAnalysis({
        ...result.profile,
        extractedText: result.extracted_text || '',
        summary: result.summary || '',
      })
    }
    await refreshResume()
    clearReport()
    setFile(null)
    setCurrentStage(null)
    setStagePercent(0)
  }

  const handleUpload = async () => {
    if (!file || navigationLockRef.current) return
    navigationLockRef.current = true
    setUploading(true)
    setError(null)
    setSuccessMessage('')
    setCurrentStage('Uploading Resume')
    setStagePercent(0)
    lastStageKeyRef.current = 'Uploading Resume'
    uploadedBytesRef.current = 0
    totalBytesRef.current = file.size || 0

    const jobId = `job_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`
    jobIdRef.current = jobId

    try {
      // Fire the upload. The await blocks until the response OR an error.
      // The polling endpoint reflects real backend progress.
      const response = await uploadResume(file, {
        jobId,
        onUploadProgress: (event) => {
          if (event.total) {
            totalBytesRef.current = event.total
            const pct = Math.round((event.loaded / event.total) * 100)
            setStagePercent(Math.min(pct, 95))
            uploadedBytesRef.current = event.loaded
          }
        },
      })

      // Most of the time the polling will have already finished. Guard
      // against the case where polling hasn't caught the result yet.
      if (currentStage !== 'Completed') {
        const payload = response?.data || {}
        if (payload.success) {
          // The backend's last _job_update was "Completed" with the result.
          setCurrentStage('Completed')
          setStagePercent(100)
          await handleUploadSuccess(payload)
        } else {
          // Fall back to trusting the JSON response.
          await handleUploadSuccess(payload)
        }
      }
    } catch (err) {
      stopPolling()
      setUploading(false)
      setCurrentStage(null)
      setStagePercent(0)
      setError(
        err.response?.data?.detail ||
          'Failed to upload resume. Please try again.',
      )
    } finally {
      navigationLockRef.current = false
    }
  }

  // Start polling only after the upload has been kicked off in the
  // background. The polling endpoint reflects real backend progress as
  // the LLM call runs.
  useEffect(() => {
    if (uploading && jobIdRef.current) {
      startPolling(jobIdRef.current)
    }
    return () => {
      if (!uploading) stopPolling()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uploading])

  const resetUpload = () => {
    setFile(null)
    setAnalysis(null)
    setError(null)
    setSuccessMessage('')
    setConfirmReplace(false)
    setCurrentStage(null)
    setStagePercent(0)
  }

  const handleViewResume = async () => {
    setViewLoading(true)
    try {
      const response = await getResumeLatestAnalysis()
      setViewingResume(response.data || null)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load resume.')
    } finally {
      setViewLoading(false)
    }
  }

  const handleDeleteResume = async () => {
    if (!confirmDelete) {
      setConfirmDelete(true)
      return
    }
    setDeleting(true)
    setError(null)
    try {
      await deleteResumeLatest()
      clearReport()
      setAnalysis(null)
      setViewingResume(null)
      setFile(null)
      await refreshResume()
      setSuccessMessage('Resume deleted. Returning to first-use state.')
      setConfirmDelete(false)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to delete resume.')
    } finally {
      setDeleting(false)
    }
  }

  const handleReplaceResume = () => {
    if (!confirmReplace) {
      setConfirmReplace(true)
      return
    }
    setConfirmReplace(false)
    setReplacing(true)
    // Show the upload zone — we keep the existing resume in the
    // backend until the user uploads the new file (the upload route
    // APPENDS a new row and the latest-resume lookup picks it up).
    setReplacing(false)
    fileInputRef.current?.click()
  }

  // ----- Render -----

  if (analysis) {
    return (
      <div className="space-y-5">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-dark-primary">Resume Analysis</h1>
          <Button
            variant="secondary"
            onClick={() => {
              resetUpload()
              navigate('/dashboard')
            }}
            size="small"
          >
            View Weekly Report
          </Button>
        </div>

        {successMessage && (
          <Card className="border-accent-lime/40 bg-accent-lime/10">
            <p className="text-sm font-semibold text-primary-700">{successMessage}</p>
          </Card>
        )}

        <Card className="border-l-4 border-l-primary-500 shadow-pipeup-lg">
          <div className="space-y-3">
            <div>
              <h2 className="text-xl font-bold text-dark-primary">
                {analysis.name || 'Unknown'}
              </h2>
              <p className="text-sm font-medium text-gray-700">
                {analysis.email} • {analysis.phone}
              </p>
              <p className="text-sm font-medium text-gray-700">{analysis.location}</p>
              {analysis.years_of_experience && (
                <p className="mt-2 inline-block rounded-full border border-primary-500/40 bg-primary-500/10 px-3 py-0.5 text-xs font-bold text-primary-700">
                  {analysis.years_of_experience} of experience
                </p>
              )}
            </div>
            {(analysis.professional_summary || analysis.summary) && (
              <p className="text-sm font-medium leading-6 text-dark-primary">
                {analysis.professional_summary || analysis.summary}
              </p>
            )}
          </div>
        </Card>

        {analysis.recommended_roles && analysis.recommended_roles.length > 0 && (
          <Card>
            <div className="space-y-3">
              <p className="text-[10px] font-bold uppercase tracking-widest text-primary-700">
                AI Recommended Roles
              </p>
              <p className="text-xs font-medium text-gray-700">
                Roles this candidate is well-suited for based on the resume.
              </p>
              <div className="flex flex-wrap gap-2">
                {analysis.recommended_roles.map((role, i) => (
                  <span
                    key={i}
                    className="rounded-pipeup border border-primary-500/40 bg-primary-500/10 px-3 py-1.5 text-xs font-semibold text-primary-700"
                  >
                    {role}
                  </span>
                ))}
              </div>
            </div>
          </Card>
        )}

        {/* Sprint 14.3 — Career Improvement Roadmap.
            Sits below the AI Recommended Roles card so the resume
            review reads top-down: who am I → what to improve. */}
        <CareerImprovementRoadmap />

        {analysis.extractedText && (
          <Card>
            <div className="space-y-3">
              <h3 className="text-base font-bold text-dark-primary">
                Extracted resume text
              </h3>
              <p className="whitespace-pre-wrap rounded-pipeup border border-border-medium bg-background-secondary p-4 font-mono text-xs leading-relaxed text-gray-800">
                {analysis.extractedText}
              </p>
            </div>
          </Card>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-1">
        <p className="text-eyebrow">Resume</p>
        <h1 className="text-display-sm">Resume Analysis</h1>
      </div>

      {/* Current Resume Management Card */}
      {currentResume && !file && !uploading && !viewingResume && (
        <CurrentResumeCard
          currentResume={currentResume}
          onView={handleViewResume}
          onReplace={handleReplaceResume}
          onDelete={handleDeleteResume}
          deleting={deleting}
          replacing={replacing}
          viewLoading={viewLoading}
        />
      )}

      {confirmReplace && (
        <Card className="border-amber-500/40 bg-amber-500/10">
          <div className="space-y-3">
            <p className="text-sm font-semibold text-amber-800">
              Replace your current resume? The new file will be analyzed and
              become your active resume. The previous report will be cleared.
            </p>
            <div className="flex gap-2">
              <Button
                size="small"
                onClick={handleReplaceResume}
                disabled={replacing}
              >
                {replacing ? 'Opening…' : 'Choose new file'}
              </Button>
              <Button
                size="small"
                variant="secondary"
                onClick={() => setConfirmReplace(false)}
              >
                Cancel
              </Button>
            </div>
          </div>
        </Card>
      )}

      {confirmDelete && (
        <Card className="border-red-500/40 bg-red-500/10">
          <div className="space-y-3">
            <p className="text-sm font-bold text-red-700">
              Delete your current resume? This will:
            </p>
            <ul className="ml-4 list-disc text-sm font-medium text-red-700">
              <li>Remove it from the database</li>
              <li>Clear any saved weekly report</li>
              <li>Return the dashboard to first-use state</li>
            </ul>
            <div className="flex gap-2">
              <Button
                size="small"
                onClick={handleDeleteResume}
                disabled={deleting}
              >
                {deleting ? 'Deleting…' : 'Yes, delete resume'}
              </Button>
              <Button
                size="small"
                variant="secondary"
                onClick={() => setConfirmDelete(false)}
              >
                Cancel
              </Button>
            </div>
          </div>
        </Card>
      )}

      {/* Upload Card */}
      <Card>
        <div
          className={`border-2 border-dashed rounded-pipeup p-10 text-center transition-all duration-300 ${
            file
              ? 'border-primary-500/50 bg-primary-500/10'
              : 'border-border-medium hover:border-accent-lime/60 hover:bg-accent-lime/5 cursor-pointer'
          }`}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
        >
          {uploading ? (
            <StageProgress currentStage={currentStage} percent={stagePercent} />
          ) : file ? (
            <div className="space-y-3">
              <div className="text-4xl">📄</div>
              <p className="text-base font-bold text-dark-primary">{file.name}</p>
              <p className="text-xs font-semibold text-gray-700">
                {(file.size / 1024).toFixed(1)} KB
              </p>
              <div className="flex justify-center gap-2">
                <Button onClick={handleUpload} size="small">
                  Analyze Resume
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => setFile(null)}
                  size="small"
                >
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <label
              htmlFor="file-input"
              className="block cursor-pointer space-y-3"
            >
              <div className="text-4xl">📤</div>
              <p className="text-base font-bold text-dark-primary">
                {currentResume ? 'Upload a new resume' : 'Drop your resume here'}
              </p>
              <p className="text-sm font-medium text-gray-700">or click to browse</p>
              <input
                type="file"
                accept=".pdf"
                onChange={(e) => handleFileSelect(e.target.files[0])}
                className="sr-only"
                id="file-input"
                ref={fileInputRef}
              />
              <span className="relative inline-flex items-center justify-center gap-2 font-bold transition-all duration-pipeup focus-within:outline-none focus-within:ring-2 focus-within:ring-accent-lime/50 focus-within:ring-offset-2 focus-within:ring-offset-background-primary bg-background-card border-2 border-border-medium text-dark-primary rounded-pipeup hover:bg-background-secondary hover:border-accent-lime/60 hover:shadow-pipeup active:scale-95 px-6 py-2.5 text-sm">
                Choose File
              </span>
              <p className="text-xs font-semibold text-gray-700">PDF files only, max 10MB</p>
            </label>
          )}
        </div>
      </Card>

      {error && (
        <Card className="border-red-500/40 bg-red-500/10">
          <p className="text-sm font-bold text-red-700">{error}</p>
        </Card>
      )}

      {successMessage && !confirmDelete && !confirmReplace && !viewingResume && (
        <Card className="border-accent-lime/40 bg-accent-lime/10">
          <p className="text-sm font-bold text-primary-700">{successMessage}</p>
        </Card>
      )}

      {/* View Resume Modal */}
      {viewingResume && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-dark-primary/60 p-4 backdrop-blur-sm">
          <div className="max-h-[85vh] w-full max-w-3xl overflow-y-auto rounded-pipeup border border-border-medium bg-background-card p-6 shadow-pipeup-xl">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-bold text-dark-primary">
                {viewingResume.profile?.name || 'Resume'}
              </h3>
              <Button
                size="small"
                variant="secondary"
                onClick={() => setViewingResume(null)}
              >
                Close
              </Button>
            </div>
            <div className="space-y-3 text-sm font-medium text-gray-800">
              <p className="font-semibold text-gray-700">
                {viewingResume.profile?.email} •{' '}
                {viewingResume.profile?.phone} •{' '}
                {viewingResume.profile?.location}
              </p>
              {viewingResume.summary && (
                <p className="leading-relaxed">{viewingResume.summary}</p>
              )}
              {Array.isArray(viewingResume.profile?.skills) &&
                viewingResume.profile.skills.length > 0 && (
                  <div>
                    <p className="mb-1.5 text-[10px] font-bold uppercase tracking-widest text-primary-700">
                      Skills
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {viewingResume.profile.skills.map((s, i) => (
                        <span
                          key={i}
                          className="rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-0.5 text-xs font-semibold text-emerald-700"
                        >
                          {s}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              {viewingResume.extracted_text && (
                <details className="rounded-pipeup border border-border-medium bg-background-secondary p-3">
                  <summary className="cursor-pointer text-[10px] font-bold uppercase tracking-widest text-gray-700">
                    Show full extracted text
                  </summary>
                  <p className="mt-2 whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-gray-800">
                    {viewingResume.extracted_text}
                  </p>
                </details>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Info Card — Sprint-9 polish: stronger hierarchy, premium icon row,
          soft hover highlight, and a top accent stripe to make this
          section feel important without becoming loud. */}
      <Card className="relative overflow-hidden">
        <span
          aria-hidden="true"
          className="absolute inset-x-0 top-0 h-0.5 bg-gradient-to-r from-accent-lime/0 via-accent-lime/70 to-accent-lime/0"
        />
        <div className="mb-4 flex items-center gap-2">
          <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-accent-lime/15 text-primary-700">
            <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
          </span>
          <h3 className="text-sm font-bold uppercase tracking-widest text-gray-700">
            What will be analyzed
          </h3>
        </div>
        <ul className="grid grid-cols-1 gap-1 sm:grid-cols-2 sm:gap-2">
          {[
            'Personal information',
            'Skills & technologies',
            'Work experience',
            'Education background',
            'Projects',
            'Certifications',
            'Key strengths',
          ].map((item) => (
            <li
              key={item}
              className="group flex items-center gap-2.5 rounded-pipeup border border-transparent px-3 py-2 text-sm font-medium text-gray-700 transition-all duration-pipeup ease-out hover:border-accent-lime/40 hover:bg-accent-lime/5 hover:text-dark-primary"
            >
              <span
                aria-hidden="true"
                className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-primary-100 text-primary-700 transition-colors duration-pipeup group-hover:bg-accent-lime group-hover:text-dark-primary"
              >
                <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
              </span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  )
}

export default ResumeUpload
