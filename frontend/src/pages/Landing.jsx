import React from 'react'
import { Link } from 'react-router-dom'
import {
  Sparkles,
  ArrowRight,
  FileText,
  Brain,
  Briefcase,
  CheckCircle2,
  Building2,
  Zap,
  Target,
  Mail,
  GitBranch,
  Bird,
} from 'lucide-react'
import Button from '../components/Button'
import Card from '../components/Card'
import Badge from '../components/Badge'
const STAGES = [
  {
    n: '01',
    title: 'Upload your resume',
    desc: 'A single PDF. We extract your skills, technologies, and recommended roles in seconds.',
    icon: FileText,
  },
  {
    n: '02',
    title: 'Match the market',
    desc: 'Our six-stage pipeline cross-references your profile with every funded AI startup we know about.',
    icon: Building2,
  },
  {
    n: '03',
    title: 'Read the briefing',
    desc: 'A personalized executive report: top opportunities, your skill gaps, career direction, and a ready-to-send cover letter.',
    icon: Briefcase,
  },
]
const FEATURES = [
  {
    icon: Brain,
    title: 'AI Resume Intelligence',
    desc: 'OpenRouter-powered extraction builds a 19-field profile — including the languages, frameworks, cloud platforms, and roles the market actually wants.',
  },
  {
    icon: Target,
    title: 'Deterministic Matching',
    desc: 'No black-box embeddings. Your matches are computed from real skill overlap, fully auditable, fully explainable.',
  },
  {
    icon: Zap,
    title: 'Live Market Data',
    desc: 'Tavily + Firecrawl + OpenRouter keep the company dataset fresh, with a 24-hour cache and a graceful Demo Data fallback.',
  },
  {
    icon: Mail,
    title: 'Cover Letter Drafts',
    desc: 'One click generates a personalized cover letter for the top match — written in the candidate\'s voice, not a template.',
  },
  {
    icon: Building2,
    title: 'Companies Explorer',
    desc: 'Browse every funded AI startup. Search, filter by sector, sort by funding, score, or recency.',
  },
  {
    icon: Sparkles,
    title: 'Career Intelligence',
    desc: 'Top hiring industries, dominant technologies in your market, and the skill gaps that will unlock the next role.',
  },
]
const Landing = () => {
  return (
    <div className="overflow-hidden">
      {/* ===========================  HERO  =========================== */}
      <section className="relative">
        <div className="bg-fade-radial absolute inset-0 -z-10" aria-hidden="true" />
        <div className="bg-grid absolute inset-0 -z-10 opacity-40" aria-hidden="true" />
        <div className="mx-auto max-w-6xl px-8 pb-20 pt-16 text-center sm:pt-20 lg:pt-24">
          <Badge tone="brand" size="md" className="mx-auto">
            <Sparkles className="h-2.5 w-2.5" />
            AI Career Intelligence
          </Badge>
          <h1 className="text-display mt-4">
            Find your <span className="text-italic-serif">career</span> at the
            <br className="hidden sm:block" />{' '}
            <span className="text-gradient-lime">world's most funded AI startups.</span>
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-base font-medium leading-7 text-gray-800">
            Upload your resume. FundFlow runs a six-stage intelligence
            pipeline to surface the companies that match you, explain
            why, and draft a personalized cover letter — in seconds.
          </p>
          <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
            <Link to="/dashboard">
              <Button size="large" rightIcon={ArrowRight}>
                Generate my weekly report
              </Button>
            </Link>
            <Link to="/companies">
              <Button size="large" variant="secondary">
                Browse 20 companies
              </Button>
            </Link>
          </div>
          <p className="mt-4 text-xs font-semibold text-gray-700">
            Free. No signup. Resume stays in your browser.
          </p>
        </div>
      </section>
      {/* ======================  THREE-STAGE WORKFLOW  ====================== */}
      <section className="mx-auto max-w-7xl px-8 pb-20 sm:px-12">
        <div className="mb-10 text-center">
          <p className="text-eyebrow">The workflow</p>
          <h2 className="text-display-sm mt-2.5">
            From PDF to a personalized AI briefing
          </h2>
          <p className="mx-auto mt-2.5 max-w-2xl text-sm font-medium text-gray-700">
            One upload, three steps. The rest runs itself.
          </p>
        </div>
        <div className="grid gap-5 md:grid-cols-3">
          {STAGES.map(({ n, title, desc, icon: Icon }) => (
            <Card key={n} padding="md" hover className="relative overflow-hidden">
              <div className="absolute -right-5 -top-5 h-20 w-20 rounded-full bg-accent-lime/8 blur-3xl" aria-hidden="true" />
              <p className="text-eyebrow text-accent-lime">Stage {n}</p>
              <Icon className="mt-3 h-6 w-6 text-primary-700" aria-hidden="true" />
              <h3 className="mt-2.5 text-base font-bold text-dark-primary">{title}</h3>
              <p className="mt-2 text-sm font-medium leading-6 text-gray-800">{desc}</p>
            </Card>
          ))}
        </div>
      </section>
      {/* ===========================  FEATURES  =========================== */}
      <section className="mx-auto max-w-7xl px-8 pb-20 sm:px-12">
        <div className="mb-10 text-center">
          <p className="text-eyebrow">What's inside</p>
          <h2 className="text-display-sm mt-2.5">
            Built for the AI era of hiring
          </h2>
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
      {/* ===========================  SOCIAL PROOF  =========================== */}
      <section className="mx-auto max-w-7xl px-8 pb-20 sm:px-12">
        <Card padding="md" className="overflow-hidden">
          <div className="grid items-center gap-6 md:grid-cols-3">
            {[
              { k: '20', v: 'AI startups indexed' },
              { k: '6', v: 'pipeline stages' },
              { k: '0', v: 'black-box embeddings' },
            ].map(({ k, v }) => (
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
      {/* ===========================  CTA  =========================== */}
      <section className="mx-auto max-w-5xl px-8 pb-20 text-center sm:px-12">
        <h2 className="text-display-sm">
          Ready to see your AI briefing?
        </h2>
        <p className="mx-auto mt-4 max-w-2xl text-sm font-medium leading-6 text-gray-800">
          It takes about 30 seconds. Upload a PDF, get a personalized report,
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
          {['No signup', 'No credit card', 'No data leaves your machine', '30 seconds to your first report'].map(
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
            <a href="#" aria-label="Bird" className="transition-colors hover:text-dark-primary duration-pipeup">
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
