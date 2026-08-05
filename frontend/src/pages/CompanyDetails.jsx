import React, { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import Card from '../components/Card'
import Button from '../components/Button'
import Loader from '../components/Loader'
import CoverLetterCard from '../components/CoverLetterCard'
import { getCompany } from '../services/companyService'
import { generateCoverLetter } from '../services/generationService'

const RECOMMENDED_ACTION = (score) => {
  if (score >= 92) {
    return {
      label: 'Apply This Week',
      detail:
        'Strong match — prioritize this company. Tailor your resume and submit within seven days.',
      tone: 'high',
    }
  }
  if (score >= 82) {
    return {
      label: 'Monitor Hiring',
      detail:
        'Solid fit — watch their job board weekly and prepare a tailored application when a strong role opens.',
      tone: 'medium',
    }
  }
  if (score >= 70) {
    return {
      label: 'Connect with Engineering Team',
      detail:
        'Worth a warm intro — reach out to engineers or hiring managers on LinkedIn before applying cold.',
      tone: 'low',
    }
  }
  return {
    label: 'Build Relevant Skills First',
    detail:
      'Close, but not a strong match yet — invest a few months in their stack before re-evaluating.',
    tone: 'neutral',
  }
}

const toneStyles = {
  high: {
    border: 'border-emerald-500/40',
    bg: 'bg-emerald-500/10',
    text: 'text-emerald-400',
  },
  medium: {
    border: 'border-primary-500/40',
    bg: 'bg-primary-500/10',
    text: 'text-primary-400',
  },
  low: {
    border: 'border-amber-500/40',
    bg: 'bg-amber-500/10',
    text: 'text-amber-400',
  },
  neutral: {
    border: 'border-dark-border',
    bg: 'bg-dark-bg/70',
    text: 'text-gray-400',
  },
}

const CompanyDetails = () => {
  const { companyName } = useParams()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [coverLetter, setCoverLetter] = useState(null)
  const [generating, setGenerating] = useState(false)
  const [generateError, setGenerateError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    setCoverLetter(null)
    setGenerateError(null)
    getCompany(companyName)
      .then((response) => {
        if (!cancelled) setData(response.data)
      })
      .catch((err) => {
        if (!cancelled) {
          setError(
            err.response?.data?.detail ||
              'Failed to load company intelligence. Please try again.',
          )
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [companyName])

  const handleGenerateCoverLetter = async () => {
    setGenerating(true)
    setGenerateError(null)
    try {
      const response = await generateCoverLetter(companyName)
      setCoverLetter(response.data)
    } catch (err) {
      setGenerateError(
        err.response?.data?.detail ||
          'Failed to generate cover letter. Please try again.',
      )
    } finally {
      setGenerating(false)
    }
  }

  if (loading) {
    return (
      <Card>
        <div className="flex flex-col items-center justify-center gap-4 py-16">
          <Loader size="large" />
          <p className="text-sm text-gray-700">Loading company intelligence…</p>
        </div>
      </Card>
    )
  }

  if (error) {
    const notFound = error.toLowerCase().includes('not found')
    return (
      <Card>
        <div className="flex flex-col items-center justify-center gap-4 py-16 text-center">
          <div className="text-5xl">🚧</div>
          <h3 className="text-xl font-semibold text-dark-primary">
            {notFound ? 'Company not found' : 'Unable to load company'}
          </h3>
          <p className="max-w-md text-sm text-gray-700">{error}</p>
          <Link to="/dashboard" className="mt-2">
            <Button variant="secondary">Back to Report</Button>
          </Link>
        </div>
      </Card>
    )
  }

  const { company, match } = data
  const action = RECOMMENDED_ACTION(match.score)
  const actionStyle = toneStyles[action.tone]

  return (
    <div className="space-y-6">
      <Link
        to="/dashboard"
        className="inline-flex items-center gap-2 text-sm font-medium text-gray-700 transition-colors hover:text-dark-primary"
      >
        <span aria-hidden="true">←</span>
        Back to Weekly Report
      </Link>

      {/* Hero */}
      <Card>
        <div className="space-y-5">
          <div className="flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
            <div className="space-y-3">
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-primary-600">
                Company Intelligence
              </p>
              <h1 className="text-3xl font-bold text-dark-primary sm:text-4xl">
                {company.name}
              </h1>
              {company.tagline && (
                <p className="max-w-2xl text-base italic leading-7 text-gray-700">
                  &ldquo;{company.tagline}&rdquo;
                </p>
              )}
              <div className="flex flex-wrap gap-2">
                {company.industry && (
                  <span className="rounded-full border border-primary-500/40 bg-primary-500/10 px-3 py-1 text-xs font-semibold text-primary-700">
                    {company.industry}
                  </span>
                )}
                {company.funding_round && (
                  <span className="rounded-full border border-emerald-500/40 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-700">
                    {company.funding_round}
                  </span>
                )}
                {company.funding_amount && (
                  <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-3 py-1 text-xs font-semibold text-amber-700">
                    {company.funding_amount}
                  </span>
                )}
                {company.headquarters && (
                  <span className="rounded-full border border-border-medium bg-background-secondary px-3 py-1 text-xs font-semibold text-gray-800">
                    {company.headquarters}
                  </span>
                )}
              </div>
            </div>

            {/* Match score — prominent card with strong visual hierarchy */}
            <div className="rounded-pipeup border-2 border-primary-500/40 bg-gradient-to-br from-primary-500/10 via-accent-lime/5 to-primary-500/10 p-6 text-center md:min-w-[200px] shadow-pipeup">
              <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
                Overall Match
              </p>
              <p className="mt-3 font-bold leading-none text-dark-primary" style={{ fontSize: '4.5rem' }}>
                {match.score}
                <span className="text-2xl font-semibold text-gray-500">/100</span>
              </p>
              <p className="mt-2 text-[11px] font-bold uppercase tracking-widest text-primary-700">
                {match.score >= 92
                  ? 'Exceptional alignment'
                  : match.score >= 82
                  ? 'Strong alignment'
                  : match.score >= 70
                  ? 'Moderate alignment'
                  : 'Limited alignment'}
              </p>
            </div>
          </div>

          {/* Score progress bar */}
          <div className="space-y-2">
            <div className="h-2 w-full overflow-hidden rounded-full bg-border-medium">
              <div
                className="h-full bg-gradient-to-r from-primary-500 to-accent-lime transition-all duration-700 ease-out"
                style={{ width: `${match.score}%` }}
              />
            </div>
          </div>
        </div>
      </Card>

      {/* Why this company */}
      {company.why_hot && (
        <Card>
          <div className="space-y-3">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
              Why This Company?
            </p>
            <p className="text-base leading-7 text-dark-primary">
              {company.why_hot}
            </p>
            {company.career_page && (
              <p className="text-sm text-gray-700">
                <span className="font-semibold text-gray-800">Careers:</span>{' '}
                <span className="font-semibold text-primary-700">{company.career_page}</span>
              </p>
            )}
          </div>
        </Card>
      )}

      {/* Match analysis */}
      <Card>
        <div className="space-y-5">
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
            AI Match Analysis
          </p>

          <div className="grid gap-5 md:grid-cols-2">
            {/* Matching skills */}
            <div>
              <p className="mb-3 text-sm font-semibold text-dark-primary">
                Matching Skills
              </p>
              {match.matching_skills.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {match.matching_skills.map((skill, i) => (
                    <span
                      key={i}
                      className="rounded-full border border-emerald-500/40 bg-emerald-500/10 px-3 py-1 text-sm font-semibold text-emerald-700"
                    >
                      {skill}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-700">
                  No direct skill overlap detected.
                </p>
              )}
            </div>

            {/* Missing skills */}
            <div>
              <p className="mb-3 text-sm font-semibold text-dark-primary">
                Skills to Highlight
              </p>
              {match.missing_skills.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {match.missing_skills.map((skill, i) => (
                    <span
                      key={i}
                      className="rounded-full border border-border-medium bg-background-secondary px-3 py-1 text-sm font-semibold text-gray-800"
                    >
                      {skill}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-700">
                  No additional skills highlighted.
                </p>
              )}
            </div>
          </div>

          {match.reason && (
            <div className="rounded-pipeup border border-border-medium bg-background-secondary p-4">
              <p className="text-xs font-bold uppercase tracking-[0.2em] text-gray-700">
                Personalized Reason
              </p>
              <p className="mt-2 text-sm leading-6 text-dark-primary">
                {match.reason}
              </p>
            </div>
          )}
        </div>
      </Card>

      {/* AI Match Summary - Ticket-013 */}
      {data.matching_summary && (
        <Card>
          <div className="space-y-3">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
              AI Match Summary
            </p>
            <p className="text-base leading-7 text-dark-primary">
              {data.matching_summary}
            </p>
          </div>
        </Card>
      )}

      {/* Your Strengths - Ticket-013 */}
      {data.matching_strengths && data.matching_strengths.length > 0 && (
        <Card>
          <div className="space-y-3">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
              Your Strengths
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              {data.matching_strengths.map((strength, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2 rounded-pipeup border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm font-semibold text-emerald-800"
                >
                  <span className="mt-0.5 font-bold text-emerald-700">✓</span>
                  <span>{strength}</span>
                </div>
              ))}
            </div>
          </div>
        </Card>
      )}

      {/* Skill Gaps - Ticket-013 */}
      {data.missing_skills && data.missing_skills.length > 0 && (
        <Card>
          <div className="space-y-3">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.2em] text-amber-700">
                Skill Gaps
              </p>
              <p className="mt-1 text-sm text-gray-700">
                Technologies they want that you haven't listed on your resume.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {data.missing_skills.map((skill, i) => (
                <span
                  key={i}
                  className="rounded-full border border-amber-500/40 bg-amber-500/10 px-3 py-1 text-sm font-semibold text-amber-800"
                >
                  {skill}
                </span>
              ))}
            </div>
          </div>
        </Card>
      )}

      {/* Recommended Learning - Ticket-013 */}
      {data.recommended_learning && data.recommended_learning.length > 0 && (
        <Card>
          <div className="space-y-3">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
              Recommended Learning
            </p>
            <ul className="space-y-2">
              {data.recommended_learning.map((item, i) => (
                <li
                  key={i}
                  className="flex items-start gap-3 text-sm leading-6 text-dark-primary"
                >
                  <span className="mt-0.5 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full border border-accent-lime/40 bg-accent-lime/10 text-xs font-bold text-primary-700">
                    ✓
                  </span>
                  <span className="font-medium">{item}</span>
                </li>
              ))}
            </ul>
          </div>
        </Card>
      )}

      {/* Career Alignment - Ticket-013 */}
      {data.career_alignment && (
        <Card className="border-primary-500/40 bg-gradient-to-br from-primary-500/10 to-accent-lime/5">
          <div className="space-y-3">
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
              Career Alignment
            </p>
            <p className="text-sm font-medium leading-7 text-dark-primary">
              {data.career_alignment}
            </p>
          </div>
        </Card>
      )}

      {/* Recommended next action */}
      <Card className={`${actionStyle.border} ${actionStyle.bg}`}>
        <div className="space-y-2">
          <p className={`text-xs font-bold uppercase tracking-[0.2em] ${actionStyle.text}`}>
            Recommended Next Action
          </p>
          <h3 className={`text-xl font-bold ${actionStyle.text}`}>
            ✓ {action.label}
          </h3>
          <p className="text-sm font-medium leading-6 text-dark-primary">{action.detail}</p>
        </div>
      </Card>

      {/* Cover letter */}
      <Card>
        <div className="space-y-4">
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
            Personalized Cover Letter
          </p>
          <p className="text-sm text-gray-700">
            Generate an AI-drafted cover letter tailored to {company.name} and
            your uploaded resume.
          </p>

          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={handleGenerateCoverLetter} disabled={generating}>
              {generating ? 'Generating Cover Letter…' : 'Generate AI Cover Letter'}
            </Button>
            {generating && <Loader size="small" />}
          </div>

          {generateError && (
            <div className="rounded-pipeup border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm font-semibold text-red-700">
              {generateError}
            </div>
          )}
        </div>
      </Card>

      {coverLetter && <CoverLetterCard coverLetter={coverLetter} />}
    </div>
  )
}

export default CompanyDetails