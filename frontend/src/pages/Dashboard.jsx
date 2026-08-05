import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Card from '../components/Card'
import Button from '../components/Button'
import CoverLetterCard from '../components/CoverLetterCard'
import { generateWeeklyReport } from '../services/workflowService'
import { getCompanies } from '../services/companyService'
import { useReport } from '../context/ReportContext'
import { useResume } from '../context/ResumeContext'

const WORKFLOW_STAGES = [
  'Reading Resume',
  'Understanding Candidate Profile',
  'Discovering High-Growth AI Companies',
  'Matching Skills',
  'Ranking Opportunities',
  'Generating Cover Letter',
  'Preparing Weekly Career Report',
]

const STAGE_TICK_MS = 1000
const COMPLETE_PAUSE_MS = 350

// User-facing summary of what the AI actually did — displayed after
// the workflow completes.
const ACTIVITY_TIMELINE = [
  { label: 'Resume Analyzed', detail: 'Profile extracted' },
  { label: 'Companies Discovered', detail: 'Funded AI startups sourced' },
  { label: 'Skills Matched', detail: 'Deterministic overlap scoring' },
  { label: 'Cover Letter Generated', detail: 'Personalized draft' },
]

const StageRow = ({ stage, state }) => {
  if (state === 'completed') {
    return (
      <li className="flex items-center gap-3 text-sm font-semibold text-primary-700 transition-all duration-pipeup">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-accent-lime/30 border border-accent-lime/40">
          <svg
            className="h-3.5 w-3.5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={3}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
        </span>
        <span>{stage}</span>
      </li>
    )
  }
  if (state === 'current') {
    return (
      <li className="flex items-center gap-3 text-sm font-bold text-dark-primary transition-all duration-pipeup">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-accent-lime/40 border border-accent-lime/50">
          <span className="h-3.5 w-3.5 animate-spin rounded-full border-3 border-accent-lime border-t-transparent" />
        </span>
        <span>{stage}</span>
      </li>
    )
  }
  return (
    <li className="flex items-center gap-3 text-sm font-medium text-gray-700 transition-all duration-pipeup">
      <span className="flex h-7 w-7 items-center justify-center rounded-full border border-border-medium bg-background-secondary">
        <span className="h-1.5 w-1.5 rounded-full bg-muted-medium" />
      </span>
      <span>{stage}</span>
    </li>
  )
}

const SnapshotCard = ({ label, value, accent = false }) => (
  <div
    className={`rounded-pipeup border p-5 transition-all duration-pipeup ${
      accent
        ? 'border-accent-lime/40 bg-accent-lime/10 shadow-pipeup-glow'
        : 'border-border-medium bg-background-card shadow-pipeup'
    }`}
  >
    <p className="text-[10px] font-bold uppercase tracking-widest text-gray-700">{label}</p>
    <p className="mt-3 text-xl font-bold text-dark-primary">{value}</p>
  </div>
)

const Insight = ({ children, tone = 'primary' }) => {
  const tones = {
    primary: 'border-accent-lime/30 bg-accent-lime/10 text-primary-700',
    emerald: 'border-semantic-success/30 bg-semantic-success/10 text-emerald-700',
    amber: 'border-semantic-warning/30 bg-semantic-warning/10 text-amber-700',
    pink: 'border-accent-lime/30 bg-accent-lime/10 text-primary-700',
  }
  return (
    <div className={`flex items-start gap-2.5 rounded-pipeup border px-4 py-2.5 ${tones[tone] || tones.primary}`}>
      <span className="mt-0.5 text-base font-bold leading-none">●</span>
      <p className="text-sm font-semibold leading-5 text-dark-primary">{children}</p>
    </div>
  )
}

const formatFunding = (millions) => {
  if (!millions && millions !== 0) return '—'
  if (millions >= 1000) return `$${(millions / 1000).toFixed(1)}B`
  return `$${millions.toFixed(0)}M`
}

const IndustryBars = ({ breakdown }) => {
  if (!breakdown || breakdown.length === 0) return null
  const max = Math.max(...breakdown.map((b) => b.company_count || 0), 1)
  return (
    <div className="space-y-2">
      {breakdown.slice(0, 8).map((row) => (
        <div key={row.industry} className="flex items-center gap-3">
          <div className="w-44 flex-shrink-0 truncate text-sm font-semibold text-dark-primary">
            {row.industry}
          </div>
          <div className="flex-1">
            <div className="h-2.5 overflow-hidden rounded-full bg-background-secondary">
              <div
                className="h-full rounded-full bg-gradient-to-r from-primary-500 to-accent-lime"
                style={{ width: `${((row.company_count || 0) / max) * 100}%` }}
              />
            </div>
          </div>
          <div className="w-10 flex-shrink-0 text-right text-sm font-bold text-dark-primary">
            {row.company_count}
          </div>
        </div>
      ))}
    </div>
  )
}

const buildAISummary = (report) => {
  const candidate = report.candidate || {}
  const rich = candidate.rich_profile || {}
  const skills = (candidate.skills || []).slice(0, 3)
  const roles = rich.recommended_roles || []
  const companiesFound = report.companies_found || 0

  const subject = skills.length
    ? `${skills.join(' + ')} profile`
    : 'engineering profile'

  const roleBit = roles.length ? ` for ${roles[0]} roles` : ''

  return `Based on your ${subject}${roleBit}, we identified ${companiesFound} relevant AI startups this week.`
}

const buildInsights = (report) => {
  const insights = []
  const candidate = report.candidate || {}
  const rich = candidate.rich_profile || {}
  const topMatches = report.top_matches || []
  const candidateSkills = candidate.skills || []

  // Insight 1: Years of experience + primary domain
  if (candidate.years_of_experience) {
    const roles = rich.recommended_roles || []
    const domain = roles.length
      ? roles[0]
      : candidate.skills?.[0] || 'your field'
    insights.push({
      tone: 'primary',
      text: `Your strongest demand area is ${domain} — ${candidate.years_of_experience} of experience aligns with current hiring.`,
    })
  }

  // Insight 2: Top skill concentration
  if (candidateSkills.length > 0 && topMatches.length > 0) {
    let topHit = null
    let topHitCount = 0
    for (const skill of candidateSkills) {
      const matched = topMatches.filter((m) =>
        (m.skills || []).some((s) => s.toLowerCase() === skill.toLowerCase()),
      ).length
      if (matched > topHitCount) {
        topHit = skill
        topHitCount = matched
      }
    }
    if (topHit && topHitCount > 0) {
      const pct = Math.round((topHitCount / topMatches.length) * 100)
      insights.push({
        tone: 'emerald',
        text: `${topHit} appears in ${pct}% of your strongest matches — your signature skill this week.`,
      })
    }
  }

  // Insight 3: Tech stack breadth
  const categories = ['frameworks', 'programming_languages', 'cloud', 'databases', 'tools']
  const filled = categories.filter((c) => (rich[c] || []).length > 0)
  if (filled.length >= 2) {
    insights.push({
      tone: 'amber',
      text: `Your tech stack spans ${filled.length} categories — ${filled.join(', ')} — giving you broad reach across AI startups.`,
    })
  }

  // Insight 4: Industry alignment
  const industries = [...new Set(topMatches.map((m) => m.industry).filter(Boolean))]
  if (industries.length > 0) {
    const list = industries.slice(0, 3).join(', ')
    insights.push({
      tone: 'pink',
      text: `Your strongest matches cluster in ${list}.`,
    })
  }

  // Insight 5: Match score average
  if (topMatches.length > 0) {
    const avg = Math.round(
      topMatches.reduce((sum, m) => sum + (m.score || 0), 0) / topMatches.length,
    )
    insights.push({
      tone: 'primary',
      text: `Average match score across your top opportunities is ${avg}/100.`,
    })
  }

  return insights.slice(0, 5)
}

const buildSnapshot = (report) => {
  const candidate = report.candidate || {}
  const rich = candidate.rich_profile || {}
  const topMatches = report.top_matches || []
  const categories = ['frameworks', 'programming_languages', 'cloud', 'databases', 'tools']

  return {
    years: candidate.years_of_experience || '—',
    skillsCount: (candidate.skills || []).length,
    techStackSize: categories.reduce((sum, c) => sum + (rich[c] || []).length, 0),
    rolesCount: (rich.recommended_roles || []).length,
    companies: report.companies_found || 0,
    topScore: topMatches[0]?.score || 0,
  }
}

const Dashboard = () => {
  const { report, setReport, clearReport, hasReport } = useReport()
  const { currentResume } = useResume()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [activeStage, setActiveStage] = useState(0)

  // Whether the empty state should be shown. A resume in the context
  // means the user has uploaded one — even if the workflow has not yet
  // run, the empty "No resume" card should never appear.
  const hasChecked = currentResume !== undefined
  const requiresResume = !currentResume && !hasReport

  // (The old on-mount `getCompanies({limit:1})` check is no longer needed:
  // ResumeContext loads the latest resume metadata on mount and exposes
  // it via useResume().)

  useEffect(() => {
    if (!loading) return

    setActiveStage(0)
    const timer = setInterval(() => {
      setActiveStage((prev) => Math.min(prev + 1, WORKFLOW_STAGES.length - 1))
    }, STAGE_TICK_MS)

    return () => clearInterval(timer)
  }, [loading])

  const handleGenerateReport = async () => {
    setLoading(true)
    setError(null)

    try {
      const response = await generateWeeklyReport()
      setActiveStage(WORKFLOW_STAGES.length - 1)
      await new Promise((resolve) => setTimeout(resolve, COMPLETE_PAUSE_MS))

      if (response.data?.requires_resume) {
        clearReport()
      } else {
        setReport(response.data)
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to generate report. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleBrowseCompanies = () => {
    const el = document.getElementById('top-opportunities')
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const stageState = (index) => {
    if (index < activeStage) return 'completed'
    if (index === activeStage) return 'current'
    return 'pending'
  }

  const progressPercent = ((activeStage + 1) / WORKFLOW_STAGES.length) * 100

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-eyebrow">Weekly Career Intelligence</p>
          <h1 className="text-display-sm mt-2">
            Your AI-powered <span className="text-italic-serif">career</span> briefing
          </h1>
          <p className="mt-2 max-w-xl text-sm text-gray-700">
            Your AI-curated view of the week's funded AI startups, matched to your profile.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            onClick={handleGenerateReport}
            disabled={loading || (hasChecked && requiresResume)}
            size="medium"
          >
            {loading ? 'Generating…' : 'Generate Weekly Report'}
          </Button>
        </div>
      </div>

      {error && (
        <Card className="border-semantic-danger/30 bg-semantic-danger/10">
          <p className="font-semibold text-semantic-danger">{error}</p>
        </Card>
      )}

      {loading && (
        <Card>
          <div className="space-y-4">
            <div className="flex items-start gap-2.5">
              <span className="mt-1.5 h-2 w-2 animate-pulse rounded-full bg-accent-lime" />
              <div className="flex-1">
                <h3 className="text-base font-bold text-dark-primary">
                  AI is analyzing your career opportunities
                </h3>
                <p
                  key={activeStage}
                  className="mt-1 text-sm font-medium text-gray-700 transition-all duration-pipeup"
                >
                  {WORKFLOW_STAGES[activeStage]}…
                </p>
              </div>
            </div>

            <div className="h-1.5 w-full overflow-hidden rounded-full bg-background-secondary">
              <div
                className="h-full bg-gradient-to-r from-primary-500 to-accent-lime transition-all duration-pipeup"
                style={{ width: `${progressPercent}%` }}
              />
            </div>

            <ul className="space-y-2">
              {WORKFLOW_STAGES.map((stage, i) => (
                <StageRow key={stage} stage={stage} state={stageState(i)} />
              ))}
            </ul>
          </div>
        </Card>
      )}

      {report && !loading && (
        <div className="space-y-5">
          {/* SECTION 1 - Hero Header */}
          <Card>
            <div className="space-y-3">
              <p className="text-eyebrow">Weekly Career Intelligence Report</p>
              <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
                <div>
                  <h2 className="text-2xl font-bold text-dark-primary">
                    {report.candidate?.name || 'Candidate'}
                  </h2>
                  <p className="mt-1 text-xs font-medium text-gray-700">
                    Generated {formatTimestamp(report.generated_at)}
                  </p>
                </div>
                <div className="rounded-pipeup border border-accent-lime/40 bg-accent-lime/10 px-4 py-2.5 text-center shadow-pipeup">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-primary-700">
                    Companies Analyzed
                  </p>
                  <p className="mt-1 text-2xl font-bold text-dark-primary">
                    {report.companies_found}
                  </p>
                </div>
              </div>
              <p className="max-w-2xl text-sm font-medium leading-6 text-gray-800">
                {buildAISummary(report)}
              </p>
            </div>
          </Card>

          {/* SECTION 1.5 - Market Intelligence (Ticket-014) */}
          {report.market_summary && (
            <div>
              <h3 className="mb-3 text-eyebrow">Market Intelligence</h3>
              <Card>
                <div className="space-y-3">
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    <div>
                      <p className="text-[10px] font-bold uppercase tracking-widest text-gray-700">
                        Companies Analyzed
                      </p>
                      <p className="mt-2 text-2xl font-bold text-dark-primary">
                        {report.market_summary.total_companies}
                      </p>
                    </div>
                    <div>
                      <p className="text-[10px] font-bold uppercase tracking-widest text-gray-700">
                        Industries Covered
                      </p>
                      <p className="mt-2 text-2xl font-bold text-dark-primary">
                        {report.market_summary.industries_covered}
                      </p>
                    </div>
                    <div>
                      <p className="text-[10px] font-bold uppercase tracking-widest text-gray-700">
                        Hiring Signals
                      </p>
                      <div className="mt-2 space-y-1.5 text-sm">
                        {Object.entries(report.market_summary.hiring_signals || {}).map(
                          ([k, v]) => (
                            <div key={k} className="flex items-center justify-between gap-2">
                              <span className="font-medium text-gray-700">{k}</span>
                              <span className="font-bold text-dark-primary">{v}</span>
                            </div>
                          ),
                        )}
                      </div>
                    </div>
                    <div>
                      <p className="text-[10px] font-bold uppercase tracking-widest text-gray-700">
                        Total Funding Tracked
                      </p>
                      <p className="mt-2 text-2xl font-bold text-dark-primary">
                        {formatFunding(report.market_summary.total_funding_millions)}
                      </p>
                    </div>
                  </div>

                  {report.industry_breakdown && report.industry_breakdown.length > 0 && (
                    <div className="border-t border-border-medium pt-3">
                      <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-gray-700">
                        Industries by Company Count
                      </p>
                      <IndustryBars breakdown={report.industry_breakdown} />
                    </div>
                  )}
                </div>
              </Card>
            </div>
          )}

          {/* SECTION 2 - Career Snapshot */}
          <div>
            <h3 className="mb-3 text-eyebrow">Career Snapshot</h3>
            <CareerSnapshot report={report} />
          </div>

          {/* SECTION 3 - AI Insights */}
          <div>
            <h3 className="mb-3 text-eyebrow">AI Insights</h3>
            <div className="grid gap-2 md:grid-cols-2">
              {buildInsights(report).map((insight, i) => (
                <Insight key={i} tone={insight.tone}>
                  {insight.text}
                </Insight>
              ))}
            </div>
          </div>

          {/* SECTION 3.5 - Career Intelligence (Ticket-014) */}
          {report.career_intelligence && (
            <div>
              <h3 className="mb-3 text-eyebrow">Career Intelligence</h3>
              <div className="space-y-3">
                <div className="grid gap-3 lg:grid-cols-2">
                  <Card>
                    <div className="space-y-2">
                      <p className="text-[10px] font-bold uppercase tracking-widest text-emerald-700">
                        Career Strengths
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {(report.top_strengths || []).length === 0 ? (
                          <p className="text-xs font-medium text-gray-700">No overlapping strengths yet.</p>
                        ) : (
                          (report.top_strengths || []).map((s, i) => (
                            <span
                              key={i}
                              className="rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-0.5 text-xs font-semibold text-emerald-700"
                            >
                              {s}
                            </span>
                          ))
                        )}
                      </div>
                    </div>
                  </Card>
                  <Card>
                    <div className="space-y-2">
                      <p className="text-[10px] font-bold uppercase tracking-widest text-amber-700">
                        Top Skill Gaps
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {(report.top_skill_gaps || []).length === 0 ? (
                          <p className="text-xs font-medium text-gray-700">No major skill gaps detected.</p>
                        ) : (
                          (report.top_skill_gaps || []).map((s, i) => (
                            <span
                              key={i}
                              className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2.5 py-0.5 text-xs font-semibold text-amber-800"
                            >
                              {s}
                            </span>
                          ))
                        )}
                      </div>
                    </div>
                  </Card>
                </div>

                <Card>
                  <div className="space-y-4">
                    <div>
                      <p className="text-[10px] font-bold uppercase tracking-widest text-primary-700">
                        Dominant Technologies in This Week's Market
                      </p>
                      <div className="mt-2 grid gap-1.5 sm:grid-cols-2 lg:grid-cols-4">
                        {(report.technology_breakdown || []).slice(0, 8).map((t, i) => (
                          <div
                            key={i}
                            className={`flex items-center justify-between rounded-pipeup border px-2.5 py-1.5 text-xs font-semibold ${
                              t.you_have_it
                                ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-800'
                                : 'border-border-medium bg-background-secondary text-gray-800'
                            }`}
                          >
                            <span>{t.technology}</span>
                            <span className="text-[10px] font-bold text-gray-600">×{t.demand_count}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="grid gap-4 border-t border-border-medium pt-4 sm:grid-cols-2">
                      <div>
                        <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-gray-700">
                          Top Hiring Industries
                        </p>
                        <div className="flex flex-wrap gap-1.5">
                          {(report.career_intelligence.top_hiring_industries || []).map(
                            (ind, i) => (
                              <span
                                key={i}
                                className="rounded-full border border-primary-500/40 bg-primary-500/10 px-2.5 py-0.5 text-xs font-semibold text-primary-700"
                              >
                                {ind}
                              </span>
                            ),
                          )}
                        </div>
                      </div>
                      <div>
                        <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-gray-700">
                          Highest Opportunity Areas
                        </p>
                        <div className="flex flex-wrap gap-1.5">
                          {(report.career_intelligence.highest_opportunity_areas || []).map(
                            (ind, i) => (
                              <span
                                key={i}
                                className="rounded-full border border-accent-lime/40 bg-accent-lime/10 px-3 py-1 text-xs font-semibold text-primary-700"
                              >
                                {ind}
                              </span>
                            ),
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                </Card>
              </div>
            </div>
          )}

          {/* SECTION 4 - Top Opportunities */}
          <div id="top-opportunities">
            <h3 className="mb-3 text-eyebrow">Top Opportunities</h3>
            <TopOpportunities topMatches={report.top_matches || []} />
          </div>

          {/* SECTION 5 - Cover Letter */}
          {report.cover_letter && (
            <div>
              <h3 className="mb-3 text-eyebrow">AI Generated Cover Letter</h3>
              <CoverLetterCard coverLetter={report.cover_letter} />
            </div>
          )}

          {/* SECTION 6 - Quick Actions */}
          <div>
            <h3 className="mb-3 text-eyebrow">Quick Actions</h3>
            <Card>
              <div className="grid gap-2 sm:grid-cols-3">
                <Link to="/resume" className="block">
                  <Button variant="secondary" className="w-full" size="small">
                    Upload New Resume
                  </Button>
                </Link>
                <Button variant="secondary" className="w-full" onClick={handleBrowseCompanies} size="small">
                  Browse Companies
                </Button>
                <Button className="w-full" onClick={handleGenerateReport} disabled={loading} size="small">
                  Generate Weekly Report
                </Button>
              </div>
            </Card>
          </div>

          {/* SECTION 7 - AI Activity Timeline */}
          <div>
            <h3 className="mb-3 text-eyebrow">AI Activity Timeline</h3>
            <Card>
              <ol className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                {ACTIVITY_TIMELINE.map((step, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-2.5 rounded-pipeup border border-border-medium bg-background-secondary p-3"
                  >
                    <span className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-semantic-success/20 text-semantic-success">
                      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    </span>
                    <div className="flex-1">
                      <p className="text-sm font-bold text-dark-primary">{step.label}</p>
                      <p className="mt-0.5 text-xs font-medium text-gray-700">{step.detail}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </Card>
          </div>
        </div>
      )}

      {!report && !loading && !error && !requiresResume && (
        <Card>
          <div className="flex flex-col items-center justify-center gap-2.5 py-12 text-center">
            <div className="text-4xl">📊</div>
            <h3 className="text-lg font-bold text-dark-primary">
              Your Executive Dashboard Awaits
            </h3>
            <p className="max-w-md text-sm text-gray-700">
              Click <span className="font-semibold text-dark-primary">Generate Weekly Career Report</span> above to see your AI-curated view of the week's funded AI startups, matched to your profile.
            </p>
          </div>
        </Card>
      )}

      {requiresResume && !loading && (
        <Card>
          <div className="flex flex-col items-center justify-center gap-3 py-12 text-center">
            <div className="text-4xl">📄</div>
            <h3 className="text-lg font-bold text-dark-primary">No resume uploaded yet</h3>
            <p className="max-w-md text-sm text-gray-700">
              Upload your resume to generate your first AI Career Report.
            </p>
            <Link to="/resume" className="mt-1">
              <Button size="small">Upload Resume</Button>
            </Link>
          </div>
        </Card>
      )}
    </div>
  )
}

const CareerSnapshot = ({ report }) => {
  const snap = buildSnapshot(report)
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
      <SnapshotCard label="Experience" value={snap.years} accent />
      <SnapshotCard label="Top Skills" value={snap.skillsCount} />
      <SnapshotCard label="Tech Stack Size" value={snap.techStackSize} />
      <SnapshotCard label="Recommended Roles" value={snap.rolesCount} />
      <SnapshotCard label="Companies Analyzed" value={snap.companies} />
      <SnapshotCard label="Top Match Score" value={`${snap.topScore}/100`} />
    </div>
  )
}

const TopOpportunities = ({ topMatches }) => (
  <div className="grid gap-3">
    {topMatches.map((match, index) => (
      <Link
        key={index}
        to={`/company/${encodeURIComponent(match.name)}`}
        className="block transition-transform duration-200 hover:-translate-y-0.5"
      >
        <Card className="p-5 cursor-pointer hover:border-primary-500/60 transition-colors">
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div className="flex-1 space-y-2">
              <div className="flex items-center gap-2.5">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-primary-500/20 text-xs font-bold text-primary-700">
                  {index + 1}
                </span>
                <h4 className="text-base font-bold text-dark-primary">{match.name}</h4>
                <span className="ml-auto text-[10px] font-bold uppercase tracking-widest text-primary-700 md:hidden">View details →</span>
              </div>

              {(match.funding_round || match.funding_amount || match.industry || match.headquarters) && (
                <div className="ml-9.5 flex flex-wrap items-center gap-2 text-xs font-medium text-gray-700">
                  {match.funding_round && (
                    <span className="rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-bold text-emerald-700">
                      {match.funding_round}
                    </span>
                  )}
                  {match.funding_amount && (
                    <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[10px] font-bold text-amber-700">
                      {match.funding_amount}
                    </span>
                  )}
                  {match.industry && <span className="font-semibold">{match.industry}</span>}
                  {match.headquarters && <span className="text-gray-600">· {match.headquarters}</span>}
                </div>
              )}

              {match.tagline && (
                <p className="ml-9.5 text-sm italic leading-5 text-gray-700">
                  &ldquo;{match.tagline}&rdquo;
                </p>
              )}

              <div className="ml-9.5 border-t border-border-medium pt-2">
                <p className="text-[10px] font-bold uppercase tracking-widest text-gray-700">
                  Why it matches
                </p>
                <p className="mt-1 text-sm font-medium leading-5 text-dark-primary">{match.reason}</p>
              </div>
            </div>

            <div className="ml-9.5 rounded-pipeup border-2 border-primary-500/40 bg-gradient-to-br from-primary-500/10 to-accent-lime/5 px-4 py-3 text-center md:ml-0 md:min-w-[140px] shadow-pipeup">
              <p className="text-[10px] font-bold uppercase tracking-widest text-primary-700">
                Match Score
              </p>
              <p className="mt-1 text-2xl font-bold text-dark-primary">
                {match.score}
                <span className="text-sm font-semibold text-gray-600">/100</span>
              </p>
            </div>
          </div>
        </Card>
      </Link>
    ))}
  </div>
)

const formatTimestamp = (iso) => {
  try {
    return new Date(iso).toLocaleString('en-US', {
      dateStyle: 'medium',
      timeStyle: 'short',
    })
  } catch {
    return iso
  }
}

export default Dashboard