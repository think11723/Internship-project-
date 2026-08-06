import React, { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  AlertTriangle,
  Award,
  CheckCircle2,
  Clock,
  Mail,
  Sparkles,
  Target,
  Timer,
  TrendingUp,
  Zap,
} from 'lucide-react'
import Card from '../components/Card'
import Button from '../components/Button'
import Loader from '../components/Loader'
import CoverLetterCard from '../components/CoverLetterCard'
import {
  STRATEGY_TONES,
  PRIORITY_TONES,
  DIFFICULTY_TONES,
  COMPETITION_TONES,
  TIER_TONES,
  ROI_TONES,
} from '../components/intelligenceTones'
import {
  getCompany,
  getCompaniesIntelligence,
} from '../services/companyService'
import { getCareerPlan } from '../services/careerService'
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

// ---------------------------------------------------------------------------
// Sprint 14.1 — Recommendation Intelligence Hub
//
// Pure-presentation components over the backend payload
// ``recommendation.intelligence`` (see recommendation_engine.py).
// Every field is rendered with graceful fallback — if the
// backend hasn't populated a field, we render nothing rather
// than a placeholder, keeping the page clean.
//
// The hub has six sections:
//   1. Strategy badge row     — strategy + confidence + priority
//   2. Reasoning              — ✓ bullet list (evidence-grounded)
//   3. Next actions           — □ checklist (actionable)
//   4. Outcome probabilities  — resume pass / interview / response
//   5. Application difficulty — difficulty + competition level
//   6. Timing                 — hiring speed + recommended window
//
// Colour tones live in ../components/intelligenceTones.js so the
// Companies card badges and the hub share one source of truth.
// ---------------------------------------------------------------------------

const HubSkeleton = () => (
  <Card>
    <div className="space-y-4" aria-hidden="true">
      <div className="flex items-center gap-2">
        <div className="skeleton h-5 w-32" />
        <div className="skeleton h-5 w-20 rounded-full" />
        <div className="skeleton h-5 w-16 rounded-full" />
      </div>
      <div className="space-y-2">
        <div className="skeleton h-3 w-full" />
        <div className="skeleton h-3 w-5/6" />
        <div className="skeleton h-3 w-4/6" />
      </div>
      <div className="grid grid-cols-3 gap-2">
        <div className="skeleton h-14" />
        <div className="skeleton h-14" />
        <div className="skeleton h-14" />
      </div>
    </div>
  </Card>
)

const HubEmptyState = () => (
  <Card className="border-dashed">
    <div className="empty-state">
      <span
        aria-hidden="true"
        className="inline-flex h-14 w-14 items-center justify-center rounded-full bg-accent-lime/15 text-primary-700 shadow-pipeup"
      >
        <Target className="h-7 w-7" aria-hidden="true" />
      </span>
      <h3 className="text-lg font-bold text-dark-primary">
        Upload your resume to receive personalized recommendations.
      </h3>
      <p className="max-w-md text-sm text-gray-700">
        Recommendation intelligence uses your skills, experience, and seniority
        to score this opportunity and prescribe an action plan.
      </p>
      <Link to="/resume">
        <Button size="small">Upload Resume</Button>
      </Link>
    </div>
  </Card>
)

const StrategyHeader = ({ strategy, confidence, priority }) => {
  const tone =
    STRATEGY_TONES[strategy] ||
    'border-border-medium bg-background-secondary text-gray-700'
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span
        className={`rounded-pipeup border-2 px-4 py-2 text-sm font-bold uppercase tracking-wider shadow-pipeup ${tone}`}
      >
        {strategy}
      </span>
      {confidence != null && confidence > 0 && (
        <span className="rounded-full border border-primary-500/40 bg-primary-500/10 px-3 py-1 text-xs font-bold text-primary-700">
          {confidence}% Confidence
        </span>
      )}
      {priority && priority !== 'SKIP' && (
        <span
          className={`rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-wider ${
            PRIORITY_TONES[priority] ||
            'border-border-medium bg-background-secondary text-gray-700'
          }`}
        >
          {priority} Priority
        </span>
      )}
    </div>
  )
}

const ReasoningBullets = ({ items }) => {
  if (!Array.isArray(items) || items.length === 0) return null
  return (
    <Card>
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 text-emerald-600" aria-hidden="true" />
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
            Why this recommendation
          </p>
        </div>
        <ul className="space-y-2.5">
          {items.slice(0, 6).map((line, i) => (
            <li key={i} className="flex items-start gap-2.5">
              <span className="mt-0.5 inline-flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-700">
                <svg
                  className="h-3 w-3"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={3}
                  aria-hidden="true"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </span>
              <span className="text-sm font-medium leading-6 text-dark-primary">
                {line}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </Card>
  )
}

const NextActionsChecklist = ({ items }) => {
  if (!Array.isArray(items) || items.length === 0) return null
  return (
    <Card>
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Zap className="h-4 w-4 text-primary-700" aria-hidden="true" />
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
            Your next actions
          </p>
        </div>
        <ul className="space-y-2.5">
          {items.slice(0, 7).map((line, i) => (
            <li key={i} className="flex items-start gap-2.5">
              <span
                aria-hidden="true"
                className="mt-0.5 inline-flex h-5 w-5 flex-shrink-0 items-center justify-center rounded border-2 border-primary-500/40 bg-background-card text-[10px] font-bold text-primary-700"
              >
                {i + 1}
              </span>
              <span className="text-sm font-medium leading-6 text-dark-primary">
                {line}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </Card>
  )
}

const ProbabilityCell = ({ label, value, suffix = '%' }) => {
  if (value == null) return null
  const pct = Math.max(0, Math.min(100, value))
  const tone =
    pct >= 70
      ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700'
      : pct >= 40
      ? 'border-primary-500/40 bg-primary-500/10 text-primary-700'
      : 'border-amber-500/40 bg-amber-500/10 text-amber-800'
  return (
    <div
      className={`rounded-pipeup border px-3 py-2.5 text-center ${tone}`}
      title={`${label}: ${pct}${suffix}`}
    >
      <p className="text-[10px] font-bold uppercase tracking-widest opacity-80">
        {label}
      </p>
      <p className="mt-1 text-2xl font-bold leading-none">
        {pct}
        <span className="text-sm font-semibold opacity-70">{suffix}</span>
      </p>
    </div>
  )
}

const ProbabilitiesPanel = ({ intel }) => {
  const a = intel.estimated_resume_pass_probability
  const b = intel.estimated_interview_probability
  const c = intel.estimated_response_probability
  if (a == null && b == null && c == null) return null
  return (
    <Card>
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <TrendingUp className="h-4 w-4 text-primary-700" aria-hidden="true" />
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
            Application outlook
          </p>
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          <ProbabilityCell label="Resume Pass" value={a} />
          <ProbabilityCell label="Interview" value={b} />
          <ProbabilityCell label="Response" value={c} />
        </div>
      </div>
    </Card>
  )
}

const ApplicationOutlookPanel = ({ intel }) => {
  const diff = intel.application_difficulty
  const comp = intel.competition_level
  if (!diff && !comp) return null
  return (
    <Card>
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Target className="h-4 w-4 text-primary-700" aria-hidden="true" />
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
            Application difficulty
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {diff && (
            <span
              className={`rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-wider ${
                DIFFICULTY_TONES[diff] ||
                'border-border-medium bg-background-secondary text-gray-700'
              }`}
            >
              {diff}
            </span>
          )}
          {comp && (
            <span
              className={`rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-wider ${
                COMPETITION_TONES[comp] ||
                'border-border-medium bg-background-secondary text-gray-700'
              }`}
            >
              {comp} competition
            </span>
          )}
        </div>
      </div>
    </Card>
  )
}

const TimingPanel = ({ intel }) => {
  const speed = intel.expected_hiring_speed
  const window = intel.recommended_application_window
  if (!speed && !window) return null
  return (
    <Card>
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Clock className="h-4 w-4 text-primary-700" aria-hidden="true" />
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
            Timing
          </p>
        </div>
        <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {speed && (
            <div>
              <dt className="text-[10px] font-bold uppercase tracking-widest text-gray-700">
                Expected hiring speed
              </dt>
              <dd className="mt-1 text-sm font-semibold text-dark-primary">
                {speed}
              </dd>
            </div>
          )}
          {window && (
            <div>
              <dt className="text-[10px] font-bold uppercase tracking-widest text-gray-700">
                Recommended window
              </dt>
              <dd className="mt-1 text-sm font-semibold text-dark-primary">
                {window}
              </dd>
            </div>
          )}
        </dl>
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Sprint 14.2 — Opportunity Intelligence section.
//
// Pure-presentation components over the backend payload
// ``recommendation.opportunity_v2`` (see
// opportunity_intelligence_v2.py). Same visual identity as the
// Recommendation Intelligence Hub above: same Card primitive,
// same colour palette, same typography, same spacing tokens.
//
// Sections in order:
//   1. Opportunity hero         — tier + score + ROI + recommended
//                                  application order (one row)
//   2. Opportunity summary      — one highlighted sentence
//   3. Strengths                — ✓ bullet list (evidence-grounded)
//   4. Risks                    — ⚠ bullet list (failure modes)
//   5. Meta grid                — time-to-apply + rank + signal
//                                  breakdown keys
// ---------------------------------------------------------------------------

const OpportunityHero = ({ opp }) => {
  const score = opp.opportunity_score
  const tier = opp.opportunity_tier
  const roi = opp.estimated_roi
  const order = opp.recommended_application_order
  if (score == null && !tier && !roi && !order) return null
  const tierTone =
    TIER_TONES[tier] ||
    'border-border-medium bg-background-secondary text-gray-700'
  const roiTone =
    ROI_TONES[roi] ||
    'border-border-medium bg-background-secondary text-gray-700'
  return (
    <div className="flex flex-wrap items-center gap-2">
      {tier && (
        <span
          className={`rounded-pipeup border-2 px-4 py-2 text-sm font-bold uppercase tracking-wider shadow-pipeup ${tierTone}`}
        >
          {tier} Tier
        </span>
      )}
      {score != null && (
        <span
          className={`rounded-full border px-3 py-1 text-xs font-bold ${tierTone}`}
          title={`Opportunity score ${score}/100`}
        >
          {Math.max(0, Math.min(100, score))}
          <span className="ml-1 opacity-70">/ 100</span>
        </span>
      )}
      {roi && (
        <span
          className={`rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-wider ${roiTone}`}
        >
          {roi} ROI
        </span>
      )}
      {order && order >= 1 && (
        <span className="rounded-full border border-primary-500/40 bg-primary-500/10 px-3 py-1 text-xs font-bold text-primary-700">
          #{order} Priority
        </span>
      )}
    </div>
  )
}

const OpportunitySummary = ({ summary }) => {
  if (!summary) return null
  return (
    <Card className="border-accent-lime/40 bg-gradient-to-br from-accent-lime/10 to-primary-500/5">
      <div className="flex items-start gap-3">
        <Sparkles
          className="mt-0.5 h-5 w-5 flex-shrink-0 text-primary-700"
          aria-hidden="true"
        />
        <div className="space-y-1">
          <p className="text-[10px] font-bold uppercase tracking-widest text-primary-700">
            Opportunity summary
          </p>
          <p className="text-base font-medium leading-7 text-dark-primary">
            {summary}
          </p>
        </div>
      </div>
    </Card>
  )
}

const OpportunityStrengths = ({ items }) => {
  if (!Array.isArray(items) || items.length === 0) return null
  return (
    <Card>
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 text-emerald-600" aria-hidden="true" />
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
            Why this opportunity is strong
          </p>
        </div>
        <ul className="space-y-2.5">
          {items.slice(0, 6).map((line, i) => (
            <li key={i} className="flex items-start gap-2.5">
              <span className="mt-0.5 inline-flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-700">
                <svg
                  className="h-3 w-3"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={3}
                  aria-hidden="true"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </span>
              <span className="text-sm font-medium leading-6 text-dark-primary">
                {line}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </Card>
  )
}

const OpportunityRisks = ({ items }) => {
  if (!Array.isArray(items) || items.length === 0) return null
  return (
    <Card>
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <AlertTriangle
            className="h-4 w-4 text-amber-700"
            aria-hidden="true"
          />
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
            Risks to consider
          </p>
        </div>
        <ul className="space-y-2.5">
          {items.slice(0, 6).map((line, i) => (
            <li key={i} className="flex items-start gap-2.5">
              <span className="mt-0.5 inline-flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-amber-500/20 text-amber-800">
                <AlertTriangle className="h-3 w-3" aria-hidden="true" />
              </span>
              <span className="text-sm font-medium leading-6 text-dark-primary">
                {line}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </Card>
  )
}

const OpportunitySignalBar = ({ label, value }) => {
  if (value == null) return null
  const pct = Math.max(0, Math.min(100, value))
  const tone =
    pct >= 60
      ? 'bg-emerald-500'
      : pct >= 30
      ? 'bg-primary-500'
      : 'bg-amber-500'
  return (
    <div>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] font-bold uppercase tracking-widest text-gray-700">
          {label}
        </span>
        <span className="text-xs font-bold text-dark-primary">{pct}</span>
      </div>
      <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-background-secondary">
        <div
          className={`h-full transition-all duration-500 ${tone}`}
          style={{ width: `${pct}%` }}
          aria-label={`${label}: ${pct}/100`}
        />
      </div>
    </div>
  )
}

const OpportunityMetaPanel = ({ opp }) => {
  const minutes = opp.estimated_time_to_apply
  const rank = opp.opportunity_rank
  const breakdown = opp.opportunity_score_signal_breakdown
  // Friendly labels for the signal-breakdown keys so the meta
  // panel reads like a coach's report rather than raw numbers.
  const SIGNAL_LABELS = {
    resume_match:            'Resume match',
    hiring_activity:         'Hiring activity',
    funding_recency:         'Funding recency',
    open_positions:          'Open positions',
    remote_friendliness:     'Remote friendliness',
    visa_support:            'Visa support',
    career_growth:           'Career growth',
    engineering_culture:     'Engineering culture',
    strategy_modifier:       'Strategy modifier',
    internship_or_graduate_bonus: 'Intern / graduate bonus',
  }
  const hasBreakdown =
    breakdown && typeof breakdown === 'object' && Object.keys(breakdown).length > 0
  if (minutes == null && rank == null && !hasBreakdown) return null
  return (
    <Card>
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Award className="h-4 w-4 text-primary-700" aria-hidden="true" />
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
            Effort &amp; signal breakdown
          </p>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {minutes != null && (
            <div className="flex items-center gap-2.5">
              <span className="inline-flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-pipeup bg-primary-500/10 text-primary-700">
                <Timer className="h-4 w-4" aria-hidden="true" />
              </span>
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-gray-700">
                  Time to apply
                </p>
                <p className="text-sm font-bold text-dark-primary">
                  {minutes} min
                </p>
              </div>
            </div>
          )}
          {rank != null && rank >= 1 && (
            <div className="flex items-center gap-2.5">
              <span className="inline-flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-pipeup bg-primary-500/10 text-primary-700">
                <Target className="h-4 w-4" aria-hidden="true" />
              </span>
              <div>
                <p className="text-[10px] font-bold uppercase tracking-widest text-gray-700">
                  Rank in your portfolio
                </p>
                <p className="text-sm font-bold text-dark-primary">
                  #{rank}
                </p>
              </div>
            </div>
          )}
        </div>
        {hasBreakdown && (
          <div className="space-y-2 border-t border-border-medium pt-3">
            <p className="text-[10px] font-bold uppercase tracking-widest text-gray-700">
              Score signals
            </p>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {Object.entries(breakdown)
                .slice(0, 8)
                .map(([k, v]) => (
                  <OpportunitySignalBar
                    key={k}
                    label={SIGNAL_LABELS[k] || k.replace(/_/g, ' ')}
                    value={typeof v === 'number' ? v : null}
                  />
                ))}
            </div>
          </div>
        )}
      </div>
    </Card>
  )
}

const OpportunityIntelligenceSection = ({
  opportunity,
  loading,
  hasResume,
}) => {
  // Same three-state visual contract as the Recommendation Hub:
  //   1. No resume                → HubEmptyState
  //   2. Resume + still loading    → HubSkeleton
  //   3. Resume + loaded           → full section
  if (!hasResume) return null
  if (loading && !opportunity) return <HubSkeleton />
  if (!opportunity) return null
  return (
    <div className="space-y-4" data-testid="opportunity-intelligence-section">
      <Card className="border-primary-500/30 bg-gradient-to-br from-primary-500/8 to-accent-lime/5">
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-primary-700" aria-hidden="true" />
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
              Opportunity Intelligence
            </p>
          </div>
          <OpportunityHero opp={opportunity} />
        </div>
      </Card>
      <OpportunitySummary summary={opportunity.opportunity_summary} />
      <OpportunityStrengths items={opportunity.opportunity_strengths} />
      <OpportunityRisks items={opportunity.opportunity_risks} />
      <OpportunityMetaPanel opp={opportunity} />
    </div>
  )
}

const RecommendationIntelligenceHub = ({
  intelligence,
  loading,
  hasResume,
}) => {
  // Three explicit visual states — never undefined / null placeholders:
  //   1. Resume not uploaded      → HubEmptyState
  //   2. Resume uploaded, loading → HubSkeleton
  //   3. Resume uploaded, loaded  → full hub (sections individually gated)
  if (!hasResume) return <HubEmptyState />
  if (loading && !intelligence) return <HubSkeleton />
  if (!intelligence) return <HubEmptyState />

  const { strategy, confidence, priority, reasoning, next_actions } = intelligence

  return (
    <div className="space-y-4" data-testid="recommendation-intelligence-hub">
      <Card className="border-accent-lime/40 bg-gradient-to-br from-accent-lime/10 via-primary-500/5 to-accent-lime/5">
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <Target className="h-4 w-4 text-primary-700" aria-hidden="true" />
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
              Recommendation Strategy
            </p>
          </div>
          <StrategyHeader
            strategy={strategy}
            confidence={confidence}
            priority={priority}
          />
        </div>
      </Card>

      <ReasoningBullets items={reasoning} />
      <NextActionsChecklist items={next_actions} />
      <ProbabilitiesPanel intel={intelligence} />
      <ApplicationOutlookPanel intel={intelligence} />
      <TimingPanel intel={intelligence} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sprint 14.3 — Career Action Plan section.
//
// Pure-presentation components over the per-company payload
// ``recommendation.{action_plan, resume_improvements,
// application_strategy, interview_prep}``. All fields are
// already produced by ``career_intelligence.generate_recommendation``;
// this section is a presentation layer only.
//
// Sections (rendered in order, all gated on data presence):
//   1. Hero              — today's #1 task + roadmap
//   2. Immediate next    — first item from action_plan.today
//   3. Weekly checklist  — action_plan.this_week
//   4. Follow-up reminders — action_plan.next_month
//   5. Skill improvements — resume_improvements.missing_keywords / ats
//   6. Resume bullet coaching — suggested_bullet_improvements
//   7. Networking plan   — derived from application_strategy booleans
//   8. Interview prep    — interview_prep.likely_topics + coding
// ---------------------------------------------------------------------------

const ActionPlanHero = ({ plan, strategy }) => {
  const today = plan?.today || []
  const firstTask = today[0]
  if (!firstTask) return null
  return (
    <Card className="border-accent-lime/40 bg-gradient-to-br from-accent-lime/15 via-primary-500/5 to-accent-lime/10">
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Target className="h-4 w-4 text-primary-700" aria-hidden="true" />
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
            Immediate next step
          </p>
        </div>
        <p className="text-base font-bold leading-7 text-dark-primary">
          {firstTask}
        </p>
        {strategy && (
          <p className="text-xs font-medium leading-5 text-gray-700">
            <span className="font-semibold text-dark-primary">Strategy:</span>{' '}
            {strategy}
          </p>
        )}
      </div>
    </Card>
  )
}

const ActionChecklist = ({ title, items, icon, iconClass = 'text-emerald-600', numbered = false }) => {
  if (!Array.isArray(items) || items.length === 0) return null
  return (
    <Card>
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <span className={iconClass} aria-hidden="true">
            {icon}
          </span>
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
            {title}
          </p>
        </div>
        <ul className="space-y-2.5">
          {items.slice(0, 6).map((line, i) => (
            <li key={i} className="flex items-start gap-2.5">
              <span
                aria-hidden="true"
                className={
                  numbered
                    ? 'mt-0.5 inline-flex h-5 w-5 flex-shrink-0 items-center justify-center rounded border-2 border-primary-500/40 bg-background-card text-[10px] font-bold text-primary-700'
                    : 'mt-0.5 inline-flex h-5 w-5 flex-shrink-0 items-center justify-center rounded border-2 border-primary-500/40 bg-background-card text-primary-700'
                }
              >
                {numbered ? (
                  i + 1
                ) : (
                  <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3} aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                )}
              </span>
              <span className="text-sm font-medium leading-6 text-dark-primary">
                {line}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </Card>
  )
}

const SkillImprovementsPanel = ({ resumeImprovements }) => {
  if (!resumeImprovements) return null
  const missing = resumeImprovements.missing_keywords || []
  const ats = resumeImprovements.ats_improvements || []
  const items = [
    ...missing.map((k) => `Add "${k}" to your skills section`),
    ...ats,
  ]
  if (items.length === 0) return null
  return (
    <Card>
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-amber-700" aria-hidden="true" />
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
            Skill improvement tasks
          </p>
        </div>
        <ul className="space-y-2.5">
          {items.slice(0, 6).map((line, i) => (
            <li key={i} className="flex items-start gap-2.5">
              <span
                aria-hidden="true"
                className="mt-0.5 inline-flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-amber-500/20 text-amber-800"
              >
                <Sparkles className="h-3 w-3" aria-hidden="true" />
              </span>
              <span className="text-sm font-medium leading-6 text-dark-primary">
                {line}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </Card>
  )
}

const NetworkingPlan = ({ applicationStrategy }) => {
  if (!applicationStrategy) return null
  const items = []
  if (applicationStrategy.contact_recruiter) {
    items.push('Reach out to the recruiter via LinkedIn or email')
  }
  if (applicationStrategy.use_linkedin) {
    items.push('Connect with current employees on LinkedIn')
  }
  if (applicationStrategy.cold_email) {
    items.push('Send a cold email to the founder or hiring manager')
  }
  if (applicationStrategy.should_apply_today) {
    items.push('Submit your application today')
  } else if (applicationStrategy.should_wait) {
    items.push('Wait for the right role to open before applying')
  }
  if (applicationStrategy.build_project_first) {
    items.push('Build a small portfolio project in their stack first')
  } else if (applicationStrategy.improve_resume_first) {
    items.push('Improve your resume before applying')
  }
  if (items.length === 0) return null
  return (
    <Card>
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Zap className="h-4 w-4 text-primary-700" aria-hidden="true" />
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
            Networking suggestions
          </p>
        </div>
        <ul className="space-y-2.5">
          {items.slice(0, 6).map((line, i) => (
            <li key={i} className="flex items-start gap-2.5">
              <span
                aria-hidden="true"
                className="mt-0.5 inline-flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-primary-500/15 text-primary-700"
              >
                <Zap className="h-3 w-3" aria-hidden="true" />
              </span>
              <span className="text-sm font-medium leading-6 text-dark-primary">
                {line}
              </span>
            </li>
          ))}
        </ul>
        {applicationStrategy.reasoning && (
          <p className="border-t border-border-medium pt-3 text-xs font-medium leading-5 italic text-gray-700">
            {applicationStrategy.reasoning}
          </p>
        )}
      </div>
    </Card>
  )
}

const InterviewPrepPanel = ({ interviewPrep }) => {
  if (!interviewPrep) return null
  const topics = interviewPrep.likely_topics || []
  const coding = interviewPrep.likely_coding_questions || []
  const system = interviewPrep.likely_system_design_topics || []
  const total = topics.length + coding.length + system.length
  if (total === 0) return null
  return (
    <Card>
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Award className="h-4 w-4 text-primary-700" aria-hidden="true" />
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
            Interview preparation focus
          </p>
        </div>
        {topics.length > 0 && (
          <div>
            <p className="mb-1.5 text-[10px] font-bold uppercase tracking-widest text-gray-700">
              Topics
            </p>
            <div className="flex flex-wrap gap-1.5">
              {topics.slice(0, 6).map((t, i) => (
                <span
                  key={i}
                  className="rounded-full border border-primary-500/40 bg-primary-500/10 px-2 py-0.5 text-[11px] font-semibold text-primary-700"
                >
                  {t}
                </span>
              ))}
            </div>
          </div>
        )}
        {coding.length > 0 && (
          <div className="border-t border-border-medium pt-2">
            <p className="mb-1.5 text-[10px] font-bold uppercase tracking-widest text-gray-700">
              Coding prep
            </p>
            <ul className="space-y-1.5">
              {coding.slice(0, 4).map((c, i) => (
                <li key={i} className="flex items-start gap-2 text-xs font-medium leading-5 text-dark-primary">
                  <span className="mt-0.5 text-primary-500">▸</span>
                  <span>{c}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
        {system.length > 0 && (
          <div className="border-t border-border-medium pt-2">
            <p className="mb-1.5 text-[10px] font-bold uppercase tracking-widest text-gray-700">
              System design
            </p>
            <ul className="space-y-1.5">
              {system.slice(0, 4).map((s, i) => (
                <li key={i} className="flex items-start gap-2 text-xs font-medium leading-5 text-dark-primary">
                  <span className="mt-0.5 text-primary-500">▸</span>
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Card>
  )
}

// Sprint 14.4 — richer networking / follow-up / interview prep
// produced by the portfolio-level ``career_action_planner`` (via
// GET /api/career-plan). Distinct from the per-company
// application_strategy / interview_prep blocks above — the
// planner output is portfolio-wide and richer in content. The
// two coexist so the user gets BOTH a per-company playbook and
// a portfolio-wide action plan.
const PlannerRicher = ({ planner }) => {
  if (!planner) return null
  const networking = planner.networking_tasks || []
  const followUp = planner.follow_up_plan || []
  const interview = planner.interview_preparation || []
  const hasAny =
    networking.length > 0 || followUp.length > 0 || interview.length > 0
  if (!hasAny) return null
  return (
    <>
      {networking.length > 0 && (
        <Card>
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Zap className="h-4 w-4 text-primary-700" aria-hidden="true" />
              <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
                Networking tasks (portfolio)
              </p>
            </div>
            <ul className="space-y-2.5">
              {networking.slice(0, 6).map((line, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2.5"
                >
                  <span
                    aria-hidden="true"
                    className="mt-0.5 inline-flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-primary-500/15 text-primary-700"
                  >
                    <Zap className="h-3 w-3" aria-hidden="true" />
                  </span>
                  <span className="text-sm font-medium leading-6 text-dark-primary">
                    {line}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </Card>
      )}
      {followUp.length > 0 && (
        <Card>
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Clock className="h-4 w-4 text-amber-700" aria-hidden="true" />
              <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
                Follow-up timeline (portfolio)
              </p>
            </div>
            <ol className="space-y-2.5">
              {followUp.slice(0, 6).map((line, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2.5"
                >
                  <span
                    aria-hidden="true"
                    className="mt-0.5 inline-flex h-5 w-5 flex-shrink-0 items-center justify-center rounded border-2 border-amber-500/40 bg-background-card text-[10px] font-bold text-amber-800"
                  >
                    {i + 1}
                  </span>
                  <span className="text-sm font-medium leading-6 text-dark-primary">
                    {line}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        </Card>
      )}
      {interview.length > 0 && (
        <Card>
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Award className="h-4 w-4 text-primary-700" aria-hidden="true" />
              <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
                Interview prep focus (portfolio)
              </p>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {interview.slice(0, 8).map((t, i) => (
                <span
                  key={i}
                  className="rounded-full border border-primary-500/40 bg-primary-500/10 px-2 py-0.5 text-[11px] font-semibold text-primary-700"
                >
                  {t}
                </span>
              ))}
            </div>
          </div>
        </Card>
      )}
    </>
  )
}

const CareerActionPlanSection = ({
  recommendation,
  loading,
  hasResume,
  planner,
}) => {
  if (!hasResume) return null
  if (loading && !recommendation) return <HubSkeleton />
  if (!recommendation) return null

  const plan = recommendation.action_plan || {}
  const resumeImprovements = recommendation.resume_improvements || null
  const applicationStrategy = recommendation.application_strategy || null
  const interviewPrep = recommendation.interview_prep || null
  const strategy = recommendation.intelligence?.strategy || ''

  const hasContent =
    (plan.today && plan.today.length > 0) ||
    (plan.this_week && plan.this_week.length > 0) ||
    (plan.next_month && plan.next_month.length > 0) ||
    plan.roadmap ||
    (resumeImprovements &&
      ((resumeImprovements.missing_keywords &&
        resumeImprovements.missing_keywords.length > 0) ||
        (resumeImprovements.ats_improvements &&
          resumeImprovements.ats_improvements.length > 0) ||
        (resumeImprovements.suggested_bullet_improvements &&
          resumeImprovements.suggested_bullet_improvements.length > 0))) ||
    (applicationStrategy && applicationStrategy.reasoning) ||
    (interviewPrep &&
      ((interviewPrep.likely_topics &&
        interviewPrep.likely_topics.length > 0) ||
        (interviewPrep.likely_coding_questions &&
          interviewPrep.likely_coding_questions.length > 0))) ||
    (planner &&
      ((planner.networking_tasks && planner.networking_tasks.length > 0) ||
        (planner.follow_up_plan && planner.follow_up_plan.length > 0) ||
        (planner.interview_preparation &&
          planner.interview_preparation.length > 0)))

  if (!hasContent) return null

  return (
    <div className="space-y-4" data-testid="career-action-plan-section">
      <Card className="border-primary-500/30">
        <div className="flex items-center gap-2">
          <TrendingUp className="h-4 w-4 text-primary-700" aria-hidden="true" />
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
            Career Action Plan
          </p>
        </div>
      </Card>
      <ActionPlanHero plan={plan} strategy={strategy} />
      <ActionChecklist
        title="Weekly checklist"
        items={plan.this_week}
        icon={<CheckCircle2 className="h-4 w-4 text-emerald-600" aria-hidden="true" />}
      />
      <ActionChecklist
        title="Follow-up reminders"
        items={plan.next_month}
        icon={<Clock className="h-4 w-4 text-amber-700" aria-hidden="true" />}
        numbered
      />
      <SkillImprovementsPanel resumeImprovements={resumeImprovements} />
      <NetworkingPlan applicationStrategy={applicationStrategy} />
      <InterviewPrepPanel interviewPrep={interviewPrep} />
      <PlannerRicher planner={planner} />
    </div>
  )
}

const CompanyDetails = () => {
  const { companyName } = useParams()
  const [data, setData] = useState(null)
  const [intelligence, setIntelligence] = useState(null)
  const [intelligenceLoading, setIntelligenceLoading] = useState(true)
  // Sprint 14.2 — Opportunity Intelligence state. Same fetch
  // pattern as ``intelligence``: the list endpoint is the only
  // place the per-company ``opportunity_v2`` payload lives, so
  // the detail page reads it from there.
  const [opportunity, setOpportunity] = useState(null)
  const [opportunityLoading, setOpportunityLoading] = useState(true)
  // Sprint 14.3 — Career Action Plan state. Holds the FULL matched
  // record from the list endpoint so the Career Action Plan section
  // can read every relevant per-company block (action_plan,
  // resume_improvements, application_strategy, interview_prep).
  const [actionPlan, setActionPlan] = useState(null)
  const [actionPlanLoading, setActionPlanLoading] = useState(true)
  // Sprint 14.4 — Portfolio-level planner state. Holds the
  // /api/career-plan response so the Career Action Plan section
  // can show the richer networking_tasks, follow_up_plan,
  // interview_preparation produced by career_action_planner.
  const [planner, setPlanner] = useState(null)
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
    setIntelligence(null)
    setIntelligenceLoading(true)
    setOpportunity(null)
    setOpportunityLoading(true)
    setActionPlan(null)
    setActionPlanLoading(true)

    // Sprint 14.1 / 14.2 / 14.4 — fetch the detail endpoint AND the
    // list endpoint AND the career-plan endpoint in parallel. The
    // list endpoint is the only place where the per-company
    // ``recommendation.intelligence`` and
    // ``recommendation.opportunity_v2`` payloads live. The
    // career-plan endpoint carries the richer
    // ``career_action_planner`` output (networking_tasks,
    // follow_up_plan, interview_preparation) aggregated over the
    // portfolio.
    Promise.all([
      getCompany(companyName),
      getCompaniesIntelligence({ limit: 100 }),
      getCareerPlan().catch(() => null),
    ])
      .then(([detailRes, companies, careerPlan]) => {
        if (cancelled) return
        setData(detailRes.data)
        const match = companies.find(
          (c) => (c.name || '').toLowerCase() === (companyName || '').toLowerCase(),
        )
        setIntelligence(match?.recommendation?.intelligence || null)
        setOpportunity(match?.recommendation?.opportunity_v2 || null)
        // Sprint 14.3 — keep the full recommendation so the Career
        // Action Plan section can read action_plan + resume_improvements
        // + application_strategy + interview_prep from one place.
        setActionPlan(match?.recommendation || null)
        // Sprint 14.4 — keep the portfolio-level planner payload
        // (null when no resume is uploaded, in which case the
        // career-plan endpoint returns the empty-state envelope).
        setPlanner(careerPlan && !careerPlan.requires_resume ? careerPlan : null)
      })
      .catch((err) => {
        if (cancelled) return
        setError(
          err.response?.data?.detail ||
            'Failed to load company intelligence. Please try again.',
        )
      })
      .finally(() => {
        if (cancelled) return
        setLoading(false)
        setIntelligenceLoading(false)
        setOpportunityLoading(false)
        setActionPlanLoading(false)
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
    <div className="space-y-7">
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

      {/* Sprint 14.1 — Recommendation Intelligence Hub.
          Sits ABOVE the legacy Recommended Next Action card so the
          most valuable surface area reads first. The legacy card is
          retained as a redundant fallback for cases where the new
          hub renders an empty state (no resume). */}
      <RecommendationIntelligenceHub
        intelligence={intelligence}
        loading={intelligenceLoading}
        hasResume={typeof match?.score === 'number' && match.score > 0}
      />

      {/* Sprint 14.2 — Opportunity Intelligence section.
          Sits DIRECTLY BELOW the Recommendation Hub so the visual
          hierarchy reads: "what should I do?" → "how strong is the
          opportunity?" → "what should I do first?" Same three-state
          visual contract as the hub above. */}
      <OpportunityIntelligenceSection
        opportunity={opportunity}
        loading={opportunityLoading}
        hasResume={typeof match?.score === 'number' && match.score > 0}
      />

      {/* Sprint 14.3 — Career Action Plan section.
          Sits DIRECTLY BELOW Opportunity Intelligence so the visual
          hierarchy reads: "what should I do?" (Recommendation) →
          "how strong is this?" (Opportunity) → "what specifically
          should I do?" (Action Plan). Same three-state visual
          contract as the hubs above. */}
      <CareerActionPlanSection
        recommendation={actionPlan}
        loading={actionPlanLoading}
        hasResume={typeof match?.score === 'number' && match.score > 0}
        planner={planner}
      />

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
          <div className="flex items-center gap-2">
            <Mail className="h-4 w-4 text-primary-700" aria-hidden="true" />
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary-700">
              Personalized Cover Letter
            </p>
          </div>
          <p className="text-sm text-gray-700">
            Generate an AI-drafted cover letter tailored to {company.name} and
            your uploaded resume.
          </p>

          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={handleGenerateCoverLetter} disabled={generating}>
              {generating ? 'Generating Cover Letter…' : 'Generate AI Cover Letter'}
            </Button>
            {generating && <Loader size="small" label="Generating cover letter" />}
          </div>

          {generateError && (
            <div
              role="alert"
              className="rounded-pipeup border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm font-semibold text-red-700"
            >
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