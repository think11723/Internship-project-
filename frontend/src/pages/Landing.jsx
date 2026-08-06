import React from 'react'
import { Link } from 'react-router-dom'
import {
  Sparkles,
  ArrowRight,
  Radar,
  Target,
  Trophy,
  Calendar,
  Send,
  FileText,
  Brain,
  Briefcase,
  CheckCircle2,
  Building2,
  Zap,
  Mail,
  GitBranch,
  Bird,
  Search,
  ClipboardList,
} from 'lucide-react'
import Button from '../components/Button'
import Card from '../components/Card'

// The five-stage pipeline — this is the product's mental model.
// Every other feature hangs off this loop.
const PIPELINE = [
  {
    n: '01',
    stage: 'Discover',
    title: 'Find recently funded AI startups',
    desc: 'Free RSS feeds (Google News, TechCrunch, Hacker News) surface real, funded companies in your window — every week.',
    icon: Radar,
  },
  {
    n: '02',
    stage: 'Match',
    title: 'Cross-reference your resume',
    desc: 'A deterministic extractor parses your PDF into skills, projects, and seniority — then maps them against every company.',
    icon: Target,
  },
  {
    n: '03',
    stage: 'Rank',
    title: 'Opportunity Score, tier S → D',
    desc: 'Each company gets a 0-100 score and a tier from 13 signals: hiring activity, funding recency, skill gap, remote, visa, and more.',
    icon: Trophy,
  },
  {
    n: '04',
    stage: 'Plan',
    title: 'A weekly Career Action Plan',
    desc: 'Today’s tasks, Mon-Fri plan, follow-up cadence, resume improvements, networking — all deterministic from the ranked portfolio.',
    icon: Calendar,
  },
  {
    n: '05',
    stage: 'Apply',
    title: 'Personalized cover letter',
    desc: 'A 250-350 word letter grounded in your resume, the company’s tagline, and the live-job requirements — no template.',
    icon: Send,
  },
]

const FEATURES = [
  {
    icon: Radar,
    title: 'RSS Discovery',
    desc: 'Open-source feeds (Google News, TechCrunch, Hacker News) — no Tavily quota, no Firecrawl bills, fully deterministic.',
  },
  {
    icon: Brain,
    title: 'Deterministic Extraction',
    desc: 'A regex-based pipeline turns RSS articles into real company records. Every field is grounded in a real signal.',
  },
  {
    icon: Building2,
    title: 'Career Enrichment',
    desc: 'Trafilatura + newspaper4k fetch the careers page. DuckDuckGo finds the company website, LinkedIn, and GitHub — never scraping those directly.',
  },
  {
    icon: Target,
    title: 'Recommendation Engine',
    desc: 'A 10-signal deterministic decision tree: Apply Immediately / This Week / LinkedIn / Cold-Email / Monitor / Wait / Build / Skip.',
  },
  {
    icon: Trophy,
    title: 'Opportunity Score (Tier S → D)',
    desc: '0-100 score + tier + ranking. Top 3 this week, top 10 overall, low priority, do-not-apply — one ranked list.',
  },
  {
    icon: Calendar,
    title: 'Career Action Planner',
    desc: 'Today’s tasks, Mon-Fri plan, resume improvements, follow-up cadence, networking — all derived from the ranked portfolio.',
  },
  {
    icon: Send,
    title: 'Cover Letter + Resume Coaching',
    desc: 'A 250-350 word letter grounded in your resume and the company’s live job requirements, plus resume optimisation suggestions.',
  },
]

const LANDING_STATS = [
  { k: '5', v: 'pipeline stages' },
  { k: '7', v: 'intelligence engines' },
  { k: '0', v: 'paid vendor APIs' },
  { k: '0', v: 'fabricated data' },
]

const Landing = () => {
  return (
    <div className="overflow-hidden">
      {/* ===========================  HERO  =========================== */}
      <section className="relative">
        <div className="bg-fade-radial absolute inset-0 -z-10" aria-hidden="true" />
        <div className="bg-grid absolute inset-0 -z-10 opacity-40" aria-hidden="true" />
        <div className="mx-auto max-w-6xl px-6 sm:px-8 pb-20 pt-14 sm:pt-16 lg:pt-20 text-center">
          <p className="text-eyebrow">Career intelligence for the AI era</p>
          <h1 className="text-display-sm mt-3">
            Five stages.{' '}
            <span className="text-italic-serif">One</span> answer to
            <br className="hidden sm:block" />{' '}
            <span className="text-gradient-lime">"where should I apply?"</span>
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-base font-medium leading-7 text-gray-800">
            FundFlow is a deterministic AI career agent. It{' '}
            <span className="font-semibold text-dark-primary">discovers</span> recently funded AI startups,{' '}
            <span className="font-semibold text-dark-primary">matches</span> them against your resume,{' '}
            <span className="font-semibold text-dark-primary">ranks</span> them by opportunity score,{' '}
            <span className="font-semibold text-dark-primary">plans</span> a weekly action list, then drafts a cover letter for your top match.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <Link to="/dashboard">
              <Button size="large" rightIcon={ArrowRight}>
                Start with a free weekly report
              </Button>
            </Link>
            <Link to="/companies">
              <Button size="large" variant="secondary">
                Browse today's companies
              </Button>
            </Link>
          </div>
          <p className="mt-5 text-xs font-semibold text-gray-700">
            Free. No signup. Your resume never leaves your machine.
          </p>
        </div>
      </section>

      {/* =====================  5-STAGE PIPELINE  ===================== */}
      <section className="mx-auto max-w-7xl px-8 pb-20 sm:px-12">
        <div className="mb-10 text-center">
          <p className="text-eyebrow">The product</p>
          <h2 className="text-display-sm mt-2.5">
            One loop. <span className="text-gradient-lime">Five stages.</span>
          </h2>
          <p className="mx-auto mt-2.5 max-w-2xl text-sm font-medium leading-7 text-gray-800">
            From "what jobs exist?" to "what should I do today?" — every step is deterministic, auditable, and grounded in real signals.
          </p>
        </div>
        <ol className="grid gap-3 md:grid-cols-3 lg:grid-cols-5 ">
          {PIPELINE.map(({ n, stage, title, desc, icon: Icon }, i) => (
            <li
              key={n}
              className={
                "list-none h-full " +
                (i < PIPELINE.length - 1
                  ? "lg:border-r lg:border-border-light lg:pr-3"
                  : "")
              }
            >
              <Card
                padding="md"
                hover
                className="relative h-full overflow-hidden transition-all duration-pipeup hover:shadow-pipeup-lg hover:border-accent-lime/80 hover:bg-accent-lime/5 hover:-translate-y-0.5"
              >
                <div className="absolute -right-5 -top-5 h-20 w-20 rounded-full bg-accent-lime/8 blur-3xl" aria-hidden="true" />
                <div className="relative flex h-full flex-col">
                  <p className="text-eyebrow text-accent-lime">Stage {n}</p>
                  <div className="mt-2.5 flex items-center gap-2">
                    <span className="flex h-7 w-7 items-center justify-center rounded-pipeup bg-accent-lime/10">
                      <Icon className="h-3.5 w-3.5 text-primary-700" aria-hidden="true" />
                    </span>
                    <span className="text-base font-bold text-dark-primary">{stage}</span>
                  </div>
                  <h3 className="mt-2.5 text-sm font-bold text-dark-primary">{title}</h3>
                  <p className="mt-2 text-sm font-medium leading-6 text-gray-800 text-balance">
                    {desc}
                  </p>
                  {/* <div className="mt-auto pt-3 text-eyebrow text-accent-lime/60">
                    Stage {n} of 5
                  </div> */}
                </div>
              </Card>
            </li>
          ))}
        </ol>
      </section>

      {/* ===========================  FEATURES  =========================== */}
      <section className="mx-auto max-w-7xl px-8 pb-20 sm:px-12">
        <div className="mb-10 text-center">
          <p className="text-eyebrow">What's inside</p>
          <h2 className="text-display-sm mt-2.5">
            Seven engines, one product
          </h2>
          <p className="mx-auto mt-2.5 max-w-2xl text-sm font-medium leading-7 text-gray-800">
            Open-source discovery + enrichment. Three-provider LLM gateway. Deterministic recommendation + opportunity + action-planning. Every output is explainable.
          </p>
        </div>
        <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, desc }) => (
            <Card key={title} padding="md" hover className="group">
              <div className="flex h-9 w-9 items-center justify-center rounded-pipeup bg-background-secondary text-primary-700 ring-1 ring-inset ring-border-light transition-colors group-hover:bg-accent-lime/10 group-hover:text-primary-700">
                <Icon className="h-4 w-4" aria-hidden="true" />
              </div>
              <h3 className="mt-3.5 text-sm font-bold text-dark-primary">{title}</h3>
              <p className="mt-2 text-sm font-medium leading-6 text-gray-800">{desc}</p>
            </Card>
          ))}
        </div>
      </section>

      {/* ===========================  STATS / SOCIAL PROOF  =========================== */}
      <section className="mx-auto max-w-7xl px-8 pb-20 sm:px-12">
        <Card padding="md" className="overflow-hidden">
          <div className="grid items-center gap-6 md:grid-cols-4">
            {LANDING_STATS.map(({ k, v }) => (
              <div key={v} className="text-center">
                <p className="text-3xl font-bold tracking-tight text-primary-700">
                  {k}
                </p>
                <p className="mt-1.5 text-xs font-semibold text-gray-700">{v}</p>
              </div>
            ))}
          </div>
        </Card>
      </section>

      {/* ===========================  HOW YOU USE IT  =========================== */}
      <section className="mx-auto max-w-7xl px-8 pb-20 sm:px-12">
        <div className="mb-10 text-center">
          <p className="text-eyebrow">How to use it</p>
          <h2 className="text-display-sm mt-2.5">
            Five minutes from signup to first ranked opportunity
          </h2>
        </div>
        <ol className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {[
            { n: '1', t: 'Upload your resume', d: 'A single PDF. We extract skills, technologies, and seniority.', icon: FileText },
            { n: '2', t: 'Click Generate', d: 'The weekly report runs the full 5-stage pipeline and writes a cached briefing.', icon: Search },
            { n: '3', t: 'Browse ranked companies', d: 'Tier S → D, sorted by opportunity score. Apply, track, or skip.', icon: ClipboardList },
            { n: '4', t: 'Get a Career Plan', d: 'A 5-day action plan with today’s tasks, follow-up cadence, and resume improvements.', icon: Calendar },
          ].map(({ n, t, d, icon: Icon }) => (
            <li key={n} className="list-none">
              <Card padding="md" className="h-full">
                <div className="flex items-center gap-3">
                  <div className="flex h-8 w-8 items-center justify-center rounded-pipeup bg-accent-lime/15 text-sm font-bold text-primary-700">
                    {n}
                  </div>
                  <Icon className="h-4 w-4 text-primary-700" aria-hidden="true" />
                </div>
                <h3 className="mt-3 text-sm font-bold text-dark-primary">{t}</h3>
                <p className="mt-1.5 text-sm font-medium leading-6 text-gray-800">{d}</p>
              </Card>
            </li>
          ))}
        </ol>
      </section>

      {/* ===========================  CTA  =========================== */}
      <section className="mx-auto max-w-5xl px-8 pb-20 text-center sm:px-12">
        <h2 className="text-display-sm">
          Ready to see your AI briefing?
        </h2>
        <p className="mx-auto mt-4 max-w-2xl text-sm font-medium leading-6 text-gray-800">
          It takes about 5 minutes. Upload a PDF, get a personalized report,
          and walk away with a cover letter you can actually send.
        </p>
        <div className="mt-6">
          <Link to="/dashboard">
            <Button size="large" rightIcon={ArrowRight}>
              Generate my weekly report
            </Button>
          </Link>
        </div>
        <ul className="mt-5 flex flex-wrap items-center justify-center gap-x-5 gap-y-1.5 text-xs font-semibold text-gray-700">
          {['No signup', 'No credit card', 'No data leaves your machine', '5 minutes to your first report'].map(
            (t) => (
              <li key={t} className="flex items-center gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" aria-hidden="true" />
                {t}
              </li>
            )
          )}
        </ul>
      </section>

      {/* ===========================  FOOTER  =========================== */}
      <footer className="border-t border-border-light">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-4 px-8 py-8 sm:flex-row sm:px-12">
          <div className="flex items-center gap-3 text-xs text-muted-medium">
            <Sparkles className="h-4 w-4 text-accent-lime" aria-hidden="true" />
            <span>FundFlow · Career intelligence for the AI era</span>
          </div>
          <div className="flex items-center gap-5 text-xs text-muted-medium">
            <a href="#" aria-label="Twitter" className="transition-colors hover:text-dark-primary duration-pipeup">
              <Bird className="h-4 w-4" />
            </a>
            <a href="#" aria-label="GitHub" className="transition-colors hover:text-dark-primary duration-pipeup">
              <GitBranch className="h-4 w-4" />
            </a>
            <a href="#" aria-label="Email" className="transition-colors hover:text-dark-primary duration-pipeup">
              <Mail className="h-4 w-4" />
            </a>
          </div>
        </div>
      </footer>
    </div>
  )
}

export default Landing
