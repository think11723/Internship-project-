import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Search } from 'lucide-react'
import Card from '../components/Card'
import Button from '../components/Button'
import {
  STRATEGY_TONES,
  PRIORITY_TONES,
  TIER_TONES,
} from '../components/intelligenceTones'
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

// Sprint 14.1 — Recommendation Intelligence badges.
// Each is a pure presentation component over the backend
// `recommendation.intelligence` payload. All fields are optional;
// the component renders nothing if the value is missing so the
// card stays clean when no resume has been uploaded.

const StrategyBadge = ({ strategy }) => {
  if (!strategy) return null
  const tone = STRATEGY_TONES[strategy] || 'border-border-medium bg-background-secondary text-gray-700'
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${tone}`}
      title={strategy}
    >
      {strategy}
    </span>
  )
}

const ConfidencePill = ({ confidence }) => {
  if (confidence == null || confidence === 0) return null
  return (
    <span className="rounded-full border border-primary-500/40 bg-primary-500/10 px-2 py-0.5 text-[10px] font-bold text-primary-700">
      {confidence}% Confidence
    </span>
  )
}

const PriorityChip = ({ priority }) => {
  if (!priority || priority === 'SKIP') return null
  const tone =
    PRIORITY_TONES[priority] ||
    'border-border-medium bg-background-secondary text-gray-700'
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${tone}`}
    >
      {priority} Priority
    </span>
  )
}

// Sprint 14.2 — Opportunity Intelligence badges.
// All values come from recommendation.opportunity_v2. The card
// surfaces only the highest-value signals (tier + score +
// application order) so the card height stays compact.

// Tier chip: a small uppercase chip carrying the S/A/B/C/D
// letter. Colour-mapped via TIER_TONES.
const TierChip = ({ tier }) => {
  if (!tier) return null
  const tone =
    TIER_TONES[tier] ||
    'border-border-medium bg-background-secondary text-gray-700'
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${tone}`}
      title={`Opportunity tier ${tier}`}
    >
      {tier} Tier
    </span>
  )
}

// Score badge: "89 / 100" with a colour band matching the tier.
// Re-uses the tier colour family for instant readability.
const OpportunityScoreBadge = ({ score, tier }) => {
  if (score == null) return null
  const clamped = Math.max(0, Math.min(100, score))
  const tone =
    TIER_TONES[tier] ||
    'border-border-medium bg-background-secondary text-gray-700'
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${tone}`}
      title={`Opportunity score ${clamped}/100`}
    >
      {clamped} / 100
    </span>
  )
}

// Application order chip: shown only when the list is sorted by
// opportunity rank and the backend has emitted a 1-based order.
// We display as "#N Priority" so the user understands it's a
// queue position, not a score.
const ApplicationOrderChip = ({ rank }) => {
  if (!rank || rank < 1) return null
  return (
    <span className="rounded-full border border-primary-500/40 bg-primary-500/10 px-2 py-0.5 text-[10px] font-bold text-primary-700">
      #{rank} Priority
    </span>
  )
}

const CompanyCard = ({ company, hasResume }) => {
  return (
    <Card
      hover
      padding="md"
      className="flex h-full flex-col"
    >
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

      {/* Sprint 14.1 — Recommendation Intelligence row.
          Renders ONLY when the backend has populated the
          per-company ``recommendation.intelligence`` block (which
          happens after a resume has been uploaded). When missing
          (no resume, or recommendation not yet built), this row
          is absent — keeping the card uncluttered and matching the
          "graceful fallback" requirement. */}
      {hasResume && company.recommendation?.intelligence && (
        <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
          <StrategyBadge strategy={company.recommendation.intelligence.strategy} />
          <ConfidencePill confidence={company.recommendation.intelligence.confidence} />
          <PriorityChip priority={company.recommendation.intelligence.priority} />
        </div>
      )}

      {/* Sprint 14.2 — Opportunity Intelligence row.
          Sits BELOW Recommendation so the user reads strategy first,
          then opportunity. Only renders when the backend has
          populated ``recommendation.opportunity_v2``. The three
          chips together communicate: how strong is this opportunity
          (tier), how does it score numerically (score), and where
          does it rank in the application queue (order). */}
      {hasResume && company.recommendation?.opportunity_v2 && (
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          <TierChip tier={company.recommendation.opportunity_v2.opportunity_tier} />
          <OpportunityScoreBadge
            score={company.recommendation.opportunity_v2.opportunity_score}
            tier={company.recommendation.opportunity_v2.opportunity_tier}
          />
          <ApplicationOrderChip
            rank={company.recommendation.opportunity_v2.recommended_application_order}
          />
        </div>
      )}

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

      <p className="mt-3 flex-1 text-sm italic leading-5 text-gray-700 line-clamp-3">
        {company.short_description
          ? `&ldquo;${company.short_description}&rdquo;`
          : '&mdash;'}
      </p>

      {!hasResume && (
        <p className="mt-2.5 rounded-pipeup border border-dashed border-border-medium bg-background-secondary px-3 py-1.5 text-[10px] font-semibold text-gray-700">
          Upload a resume to personalize.
        </p>
      )}

      <div className="mt-5">
        <Link
          to={`/company/${encodeURIComponent(company.name)}`}
          className="block"
        >
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
      <div
        className="grid gap-5 md:grid-cols-2 lg:grid-cols-3"
        role="status"
        aria-label="Loading companies"
      >
        {Array.from({ length: 6 }).map((_, i) => (
          <Card key={i} padding="md" className="space-y-3">
            <div className="h-5 w-3/4 skeleton" />
            <div className="h-3 w-1/2 skeleton" />
            <div className="flex gap-1.5 pt-1">
              <div className="h-4 w-16 skeleton" />
              <div className="h-4 w-12 skeleton" />
            </div>
            <div className="space-y-1.5 pt-2">
              <div className="h-3 w-full skeleton" />
              <div className="h-3 w-5/6 skeleton" />
            </div>
          </Card>
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <Card className="error-state">
        <div
          aria-hidden="true"
          className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-semantic-danger/15 text-semantic-danger"
        >
          <Search className="h-6 w-6" />
        </div>
        <h3 className="text-base font-bold text-dark-primary">
          We couldn&rsquo;t load companies.
        </h3>
        <p className="max-w-md text-sm font-medium text-gray-700">{error}</p>
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
      <div
        className="flex flex-wrap gap-2"
        role="group"
        aria-label="Filter by industry"
      >
        {INDUSTRY_FILTERS.map((f) => {
          const active = filter === f.id
          return (
            <button
              key={f.id}
              onClick={() => setFilter(f.id)}
              aria-pressed={active}
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
          {/* Sprint-9 polish: standardised empty state with premium
              icon and consistent spacing. */}
          <div className="empty-state">
            <span
              aria-hidden="true"
              className="inline-flex h-14 w-14 items-center justify-center rounded-full bg-accent-lime/15 text-primary-700 shadow-pipeup"
            >
              <Search className="h-7 w-7" aria-hidden="true" />
            </span>
            <p className="text-base font-bold text-dark-primary">No companies match your filters.</p>
            <p className="max-w-sm text-sm text-gray-700">
              Try clearing the search or broadening the industry filter.
            </p>
            <button
              onClick={() => {
                setSearch('')
                setFilter('all')
              }}
              className="btn-secondary mt-2"
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