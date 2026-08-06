// Sprint 14.1 — shared Recommendation Intelligence tones.
// Single source of truth for the colour-coding of strategy strings,
// priority bands, difficulty levels, and competition levels
// returned by the backend recommendation_engine.
//
// Kept in a tiny module (no React) so it can be unit-tested in
// isolation and imported from both Companies.jsx (card badges) and
// CompanyDetails.jsx (intelligence hub) without circular imports.

// Strategy → colour-coded chip. Strategy strings come from
// recommendation_engine.STRATEGY_THRESHOLDS. The mapping below
// keeps the visual hierarchy clear: HIGH-action strategies
// (Apply Immediately / This Week) get the primary lime accent;
// MEDIUM strategies get a softer primary tone; LOW/SKIP strategies
// fade into neutral grey.
export const STRATEGY_TONES = {
  'Apply Immediately':            'border-accent-lime/50 bg-accent-lime/15 text-primary-700',
  'Apply This Week':               'border-accent-lime/50 bg-accent-lime/15 text-primary-700',
  'Connect on LinkedIn First':     'border-primary-500/40 bg-primary-500/10 text-primary-700',
  'Cold Email Founder':            'border-primary-500/40 bg-primary-500/10 text-primary-700',
  'Monitor Hiring':                'border-border-medium bg-background-secondary text-gray-700',
  'Wait Until Next Funding Round': 'border-border-medium bg-background-secondary text-gray-700',
  'Build Missing Skills First':    'border-amber-500/40 bg-amber-500/10 text-amber-800',
  'Gain More Experience':          'border-amber-500/40 bg-amber-500/10 text-amber-800',
  'Track Future Openings':         'border-border-medium bg-background-secondary text-gray-700',
  'Not Recommended':               'border-border-medium bg-background-secondary text-gray-700',
}

// Priority → colour band. SKIP is intentionally not mapped — the
// UI never renders a SKIP chip (it would be noise).
export const PRIORITY_TONES = {
  HIGH:   'border-emerald-500/50 bg-emerald-500/15 text-emerald-700',
  MEDIUM: 'border-primary-500/50 bg-primary-500/10 text-primary-700',
  LOW:    'border-amber-500/50 bg-amber-500/10 text-amber-800',
}

// Application difficulty → colour band.
export const DIFFICULTY_TONES = {
  Easy:       'border-emerald-500/50 bg-emerald-500/15 text-emerald-700',
  Medium:     'border-primary-500/50 bg-primary-500/10 text-primary-700',
  Hard:       'border-amber-500/50 bg-amber-500/10 text-amber-800',
  'Very Hard': 'border-red-500/50 bg-red-500/15 text-red-700',
}

// Competition level → colour band.
export const COMPETITION_TONES = {
  low:    'border-emerald-500/50 bg-emerald-500/15 text-emerald-700',
  medium: 'border-primary-500/50 bg-primary-500/10 text-primary-700',
  high:   'border-red-500/50 bg-red-500/15 text-red-700',
}

// Sprint 14.2 — Opportunity tier → colour band. Tier strings come
// from opportunity_intelligence_v2.TIER_THRESHOLDS. The visual
// hierarchy is S (best, lime) → A (emerald) → B (primary) → C
// (amber) → D (red, skip).
export const TIER_TONES = {
  S: 'border-accent-lime/60 bg-accent-lime/25 text-primary-700',
  A: 'border-emerald-500/50 bg-emerald-500/15 text-emerald-700',
  B: 'border-primary-500/50 bg-primary-500/10 text-primary-700',
  C: 'border-amber-500/50 bg-amber-500/15 text-amber-800',
  D: 'border-red-500/50 bg-red-500/15 text-red-700',
}

// Sprint 14.2 — Opportunity ROI → colour band. ROI strings come
// from opportunity_intelligence_v2._expected_roi().
export const ROI_TONES = {
  High:   'border-emerald-500/50 bg-emerald-500/15 text-emerald-700',
  Medium: 'border-primary-500/50 bg-primary-500/10 text-primary-700',
  Low:    'border-border-medium bg-background-secondary text-gray-700',
}
