import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import Card from '../components/Card'
import Button from '../components/Button'
import { getCompanies } from '../services/companyService'

const INDUSTRY_FILTERS = [
  {
    id: 'all',
    label: 'All',
    match: null,
  },
  // Sprint 4 B5: chips now match the actual industries present in
  // backend/app/data/seed_companies.json (and any future live
  // discoveries). Previously three chips referenced industries
  // ('Fintech AI', 'Health AI', 'Security') that never appeared in
  // any record, so those filters silently returned zero results.
  {
    id: 'ai-research',
    label: 'AI Research',
    match: ['AI Research'],
  },
  {
    id: 'ai-platform',
    label: 'AI Platform',
    match: ['AI Platform'],
  },
  {
    id: 'foundation-models',
    label: 'Foundation Models',
    match: ['Foundation Models'],
  },
  {
    id: 'developer-tools',
    label: 'Developer Tools',
    match: ['Developer Tools'],
  },
  {
    id: 'infrastructure',
    label: 'AI Infrastructure',
    match: ['AI Infrastructure', 'MLOps', 'AI Silicon'],
  },
  {
    id: 'enterprise-ai',
    label: 'Enterprise AI',
    match: ['Enterprise AI', 'Enterprise Search', 'Vertical AI'],
  },
  {
    id: 'generative-ai',
    label: 'Generative AI',
    match: ['Generative AI', 'Generative Video'],
  },
  {
    id: 'computer-vision',
    label: 'Computer Vision',
    match: ['Computer Vision'],
  },
  {
    id: 'ai-search',
    label: 'AI Search',
    match: ['AI Search'],
  },
]

const SORT_OPTIONS = [
  { id: 'match', label: 'Highest Match' },
  { id: 'funding', label: 'Funding' },
  { id: 'newest', label: 'Newest' },
  { id: 'alpha', label: 'Alphabetical' },
]

const FUNDING_UNIT_MULTIPLIER = { K: 0.001, M: 1, B: 1000 }

function parseFundingAmount(s) {
  if (!s) return 0
  const match = String(s).match(/\$?(\d+(?:\.\d+)?)\s*([KMB])?/i)
  if (!match) return 0
  const num = parseFloat(match[1])
  const unit = (match[2] || 'M').toUpperCase()
  return num * (FUNDING_UNIT_MULTIPLIER[unit] || 1)
}

function matchesFilter(company, filterId) {
  if (filterId === 'all') return true
  const filter = INDUSTRY_FILTERS.find((f) => f.id === filterId)
  if (!filter || !filter.match) return true
  return filter.match.includes(company.industry)
}

function matchesSearch(company, query) {
  if (!query) return true
  const q = query.toLowerCase()
  return (
    (company.name || '').toLowerCase().includes(q) ||
    (company.industry || '').toLowerCase().includes(q) ||
    (company.short_description || '').toLowerCase().includes(q) ||
    (company.headquarters || '').toLowerCase().includes(q) ||
    (company.funding_stage || '').toLowerCase().includes(q)
  )
}

function sortCompanies(companies, sortId) {
  const sorted = [...companies]
  if (sortId === 'match') {
    sorted.sort((a, b) => (b.match_score ?? -1) - (a.match_score ?? -1))
  } else if (sortId === 'funding') {
    sorted.sort(
      (a, b) => parseFundingAmount(b.funding_amount) - parseFundingAmount(a.funding_amount),
    )
  } else if (sortId === 'newest') {
    sorted.sort(
      (a, b) =>
        parseInt(b.founded_year || '0', 10) - parseInt(a.founded_year || '0', 10),
    )
  } else if (sortId === 'alpha') {
    sorted.sort((a, b) => (a.name || '').localeCompare(b.name || ''))
  }
  return sorted
}

const HiringBadge = ({ status }) => {
  if (!status) return null
  const tone =
    status === 'Actively hiring'
      ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700'
      : status === 'Hiring'
      ? 'border-primary-500/40 bg-primary-500/10 text-primary-700'
      : 'border-border-medium bg-background-secondary text-gray-800'
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${tone}`}
    >
      {status}
    </span>
  )
}

const ScoreBadge = ({ score }) => (
  <span className="rounded-full border border-primary-500/40 bg-primary-500/10 px-2 py-0.5 text-[10px] font-bold text-primary-700">
    {score}/100
  </span>
)

const CompanyCard = ({ company, hasResume }) => {
  return (
    <Card className="flex h-full flex-col p-6 hover:border-primary-500/40 hover:shadow-pipeup-lg transition-all duration-pipeup">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-base font-bold text-dark-primary">
            {company.name || 'Unknown'}
          </h3>
          {(company.funding_stage ||
            company.funding_amount ||
            company.industry ||
            company.headquarters) && (
            <p className="mt-1.5 truncate text-xs font-medium text-gray-700">
              {company.industry && <span className="font-semibold">{company.industry}</span>}
              {company.industry && (company.funding_stage || company.funding_amount) && (
                <span className="mx-1.5 text-gray-500">·</span>
              )}
              {company.funding_stage && <span>{company.funding_stage}</span>}
              {company.funding_stage && company.funding_amount && (
                <span className="mx-1.5 text-gray-500">·</span>
              )}
              {company.funding_amount && <span className="font-semibold text-amber-700">{company.funding_amount}</span>}
              {company.headquarters && (
                <>
                  <span className="mx-1.5 text-gray-500">·</span>
                  <span>{company.headquarters}</span>
                </>
              )}
            </p>
          )}
        </div>
        {company.founded_year && (
          <span className="flex-shrink-0 text-xs font-bold text-gray-700">
            {company.founded_year}
          </span>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <HiringBadge status={company.hiring_status} />
        {hasResume && company.match_score != null && (
          <ScoreBadge score={company.match_score} />
        )}
        {company.company_size && (
          <span className="rounded-full border border-border-medium bg-background-secondary px-2 py-0.5 text-[10px] font-semibold text-gray-800">
            {company.company_size} people
          </span>
        )}
      </div>

      {hasResume &&
        Array.isArray(company.matching_skills) &&
        company.matching_skills.length > 0 && (
          <div className="mt-3">
            <p className="mb-1.5 text-[10px] font-bold uppercase tracking-widest text-gray-700">
              Top Matching Skills
            </p>
            <div className="flex flex-wrap gap-1">
              {company.matching_skills.slice(0, 3).map((skill, i) => (
                <span
                  key={i}
                  className="rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-700"
                >
                  {skill}
                </span>
              ))}
            </div>
          </div>
        )}

      <p className="mt-3 flex-1 text-sm italic leading-5 text-gray-700">
        {company.short_description
          ? `&ldquo;${company.short_description}&rdquo;`
          : '&mdash;'}
      </p>

      {!hasResume && (
        <p className="mt-2.5 rounded-lg border border-dashed border-border-medium bg-background-secondary px-2.5 py-1.5 text-[10px] font-semibold text-gray-700">
          Upload a resume to personalize.
        </p>
      )}

      <div className="mt-4">
        <Link to={`/company/${encodeURIComponent(company.name)}`}>
          <Button size="small" className="w-full">
            View Details
          </Button>
        </Link>
      </div>
    </Card>
  )
}

const Companies = () => {
  const [companies, setCompanies] = useState([])
  const [hasResume, setHasResume] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('all')
  const [sort, setSort] = useState('match')

  useEffect(() => {
    getCompanies()
      .then((response) => {
        const data = response.data || {}
        setCompanies(Array.isArray(data.companies) ? data.companies : [])
        setHasResume(Boolean(data.has_resume))
        setLoading(false)
      })
      .catch((err) => {
        console.error('Companies fetch failed:', err)
        setError('Failed to load companies. Please try again.')
        setLoading(false)
      })
  }, [])

  const visible = useMemo(() => {
    const filtered = companies
      .filter((c) => matchesFilter(c, filter))
      .filter((c) => matchesSearch(c, search))
    return sortCompanies(filtered, sort)
  }, [companies, search, filter, sort])

  if (loading) {
    return (
      <Card>
        <div className="flex flex-col items-center justify-center gap-3 py-12 text-center">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary-500 border-t-transparent" />
          <p className="text-sm font-semibold text-gray-800">Loading companies…</p>
        </div>
      </Card>
    )
  }

  if (error) {
    return (
      <Card className="border-red-500/40 bg-red-500/10">
        <p className="text-sm font-semibold text-red-700">{error}</p>
      </Card>
    )
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.24em] text-primary-700">
            Company Explorer
          </p>
          <h1 className="mt-2 text-2xl font-bold text-dark-primary">
            Discover Funded AI Startups
          </h1>
          <p className="mt-1.5 max-w-2xl text-sm font-medium text-gray-700">
            Browse every company in this week's intelligence run.
            {!hasResume &&
              ' Upload a resume to see personalized match scores and skill alignments.'}
          </p>
        </div>
        <div className="text-sm font-semibold text-gray-700">
          <span className="text-2xl font-bold text-dark-primary">{visible.length}</span>
          <span className="ml-1">/ {companies.length} companies</span>
        </div>
      </div>

      {/* Search */}
      <Card>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search companies..."
              className="w-full rounded-pipeup border border-border-medium bg-background-card px-3 py-2.5 text-sm font-medium text-dark-primary placeholder-muted-medium focus:border-accent-lime focus:outline-none focus:ring-2 focus:ring-accent-lime/20"
            />
          </div>
          <div className="flex items-center gap-2 text-sm font-semibold text-gray-700">
            <span className="hidden sm:inline">Sort by</span>
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value)}
              className="rounded-pipeup border border-border-medium bg-background-card px-3 py-2 text-sm font-semibold text-dark-primary focus:border-accent-lime focus:outline-none focus:ring-2 focus:ring-accent-lime/20"
            >
              {SORT_OPTIONS.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </Card>

      {/* Industry filter chips */}
      <div className="flex flex-wrap gap-2">
        {INDUSTRY_FILTERS.map((f) => {
          const active = filter === f.id
          return (
            <button
              key={f.id}
              onClick={() => setFilter(f.id)}
              className={`rounded-pipeup border px-3 py-1.5 text-xs font-bold transition-all duration-pipeup ${
                active
                  ? 'border-primary-500/40 bg-primary-500/10 text-primary-700 shadow-pipeup'
                  : 'border-border-medium bg-background-card text-gray-800 hover:border-primary-500/30 hover:bg-primary-500/5 hover:text-primary-700'
              }`}
            >
              {f.label}
            </button>
          )
        })}
      </div>

      {/* Grid */}
      {visible.length === 0 ? (
        <Card>
          <div className="flex flex-col items-center justify-center gap-2.5 py-12 text-center">
            <div className="text-3xl">🔍</div>
            <p className="text-sm font-semibold text-dark-primary">No companies match your filters.</p>
            <button
              onClick={() => {
                setSearch('')
                setFilter('all')
              }}
              className="text-sm font-bold text-primary-700 hover:underline"
            >
              Clear filters
            </button>
          </div>
        </Card>
      ) : (
        <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
          {visible.map((company) => (
            <CompanyCard
              key={company.id}
              company={company}
              hasResume={hasResume}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export default Companies