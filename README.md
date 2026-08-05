# FundFlow AI

**AI Career Intelligence Platform** that turns a single resume upload into a personalized weekly briefing of funded AI startups - ranked, explained, and paired with a ready-to-send cover letter.

---

## 1. Project Overview

FundFlow AI is an internship-MVP demonstrating a complete "career intelligence agent" in three days of development:

- **Upload once.** AI extracts a 19-field rich profile from your resume.
- **Every "Generate Weekly Career Report" click** runs a six-stage deterministic pipeline that combines your profile with a live-or-cached market dataset of funded AI startups.
- **Output** is a single dashboard: a personalized AI summary, a snapshot of your career, deterministic AI insights, the top-3 ranked opportunities with reasoning, a personalized cover letter for the #1 match, a full Companies Explorer, and an explainable AI report per company.

The product is intentionally **boring-infrastructure, smart-experience**: deterministic matching with deterministic reasoning, augmented by a single LLM call (cover letter) routed through OpenRouter.

---

## 2. Features

- **AI Resume Intelligence** - 19-field extraction via OpenRouter including `years_of_experience`, `programming_languages`, `frameworks`, `cloud`, `databases`, `tools`, `recommended_roles`.
- **Real Weekly Company Discovery** - Tavily search + Firecrawl scrape + OpenRouter normalization, with a 24h local cache and Demo Data fallback.
- **Six-Stage Orchestration** - Resume → Market → Company → Career → Ranking → Report, each with one responsibility.
- **Executive Dashboard** - hero, snapshot stats, deterministic AI insights, ranked top opportunities, AI cover letter, quick actions, activity timeline.
- **Companies Explorer** - browse all discovered companies with search, industry filter chips, sort dropdown, match scores, and skill gaps.
- **Explainable Company Details** - per-company AI match summary, strengths, skill gaps, recommended learning, career alignment.
- **AI Cover Letter Generation** - on-demand cover letter for any company, with copy + download.
- **Graceful Degradation** - no API key? Demo Data fallback. LLM failure? `null` cover letter, never a crash.

---

## 3. Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Frontend (React 18 + Vite + Tailwind)                                 │
│  ┌────────┬────────────┬──────────────┬──────────────────┐               │
│  │Landing│ Dashboard  │ Companies    │ CompanyDetails   │               │
│  └────────┴────────────┴──────────────┴──────────────────┘               │
└──────────────────────────────────────────────────────────────────────────┘
                                  │ REST (axios)
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  FastAPI Backend                                                        │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐      │
│  │ /api/resume/     │  │ /api/workflow/   │  │ /api/companies   │      │
│  │   upload         │  │   weekly-report  │  │   (list + one)   │      │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘      │
│  ┌──────────────────┐                                                   │
│  │ /api/documents/  │                                                   │
│  │   generate       │                                                   │
│  └──────────────────┘                                                   │
└──────────────────────────────────────────────────────────────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        ▼                         ▼                         ▼
┌─────────────────┐    ┌──────────────────────┐    ┌──────────────────┐
│ Resume          │    │ Orchestrator          │    │ Routes            │
│ Intelligence    │    │ run_weekly_report()  │    │ companies.py      │
│ Service         │    │   ┌────────────────┐  │    │ documents.py      │
│ (PDF + LLM)     │    │   │ Stage 1 Resume  │  │    │ health.py         │
│                 │    │   │ Stage 2 Market  │  │    │ resume.py         │
└─────────────────┘    │   │ Stage 3 Company  │  │    │ workflow.py       │
        │              │   │ Stage 4 Career   │  │    └──────────────────┘
        │              │   │ Stage 5 Ranking  │  │
        │              │   │ Stage 6 Report   │  │
        │              │   └────────────────┘  │
        │              │           │            │
        │              │           ▼            │
        │              │   ┌───────────────┐    │
        │              │   │ Intelligence  │    │
        │              │   │ Service        │    │
        │              │   │ (Market +      │    │
        │              │   │  Career)       │    │
        │              │   └───────────────┘    │
        │              │           │            │
        │              │           ▼            │
        │              │   ┌───────────────┐    │
        │              │   │ Generation    │    │
        │              │   │ Service        │    │
        │              │   │ (Cover Letter) │    │
        │              │   └───────────────┘    │
        │              └──────────────────────┘
        │                          │
        ▼                          ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Persistence                                                            │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐      │
│  │ SQLite           │  │ Local file cache │  │ seed_companies   │      │
│  │ (Resume table)   │  │ (latest_discov.. │  │ .json (Demo Data)│      │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘      │
└──────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
                       ┌─────────────────────┐
                       │ External APIs        │
                       │  • OpenRouter (LLM)  │
                       │  • Tavily (search)   │
                       │  • Firecrawl (scrape)│
                       └─────────────────────┘
```

---

## 4. Folder Structure

```
Pratik_Assignment/
├── README.md                  ← this file
├── backend/
│   ├── .env.example           ← copy to .env, fill in keys
│   ├── main.py                ← FastAPI app factory + route registration
│   ├── requirements.txt
│   ├── app/
│   │   ├── core/              ← config, logging
│   │   ├── db/                ← SQLAlchemy session
│   │   ├── models/            ← SQLAlchemy models (resume table)
│   │   ├── schemas/           ← Pydantic request/response schemas
│   │   ├── api/routes/        ← FastAPI routers
│   │   │   ├── health.py
│   │   │   ├── resume.py
│   │   │   ├── companies.py
│   │   │   ├── documents.py
│   │   │   └── workflow.py
│   │   ├── services/          ← business logic
│   │   │   ├── resume_service.py     ← PDF → AI extraction
│   │   │   ├── orchestrator.py       ← six-stage pipeline
│   │   │   ├── intelligence.py       ← market + career aggregation
│   │   │   ├── generation_service.py ← cover letter
│   │   │   ├── discovery_service.py  ← Tavily + Firecrawl + LLM
│   │   │   └── llm_service.py        ← OpenRouter client
│   │   └── tools/
│   │       └── document_parser.py     ← PyMuPDF + pdfplumber
│   └── data/
│       └── seed_companies.json ← Demo Data fallback (20 AI startups)
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── index.html
│   ├── .env.example
│   └── src/
│       ├── main.jsx           ← React entry
│       ├── App.jsx            ← Router
│       ├── index.css          ← Tailwind globals
│       ├── components/        ← Reusable UI (Button, Card, Loader, ...)
│       ├── layouts/           ← Layout shell (Navbar + Sidebar)
│       ├── pages/             ← Top-level routes
│       │   ├── Landing.jsx
│       │   ├── Dashboard.jsx   ← Executive dashboard
│       │   ├── Companies.jsx   ← Companies Explorer
│       │   ├── CompanyDetails.jsx
│       │   └── ResumeUpload.jsx
│       └── services/          ← Axios wrappers per resource
```

---

## 5. Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| **Backend framework** | FastAPI 0.104 | Async, type-driven, auto OpenAPI docs at `/docs` |
| **Database** | SQLite + SQLAlchemy 2.0 | Single table (`resumes`); file-backed |
| **PDF parsing** | PyMuPDF + pdfplumber | Primary + fallback |
| **LLM SDK** | openai 1.3.7 (Python) | Pointed at OpenRouter via `base_url` |
| **LLM provider** | OpenRouter | OpenAI-compatible API |
| **Web search** | Tavily | News domain-restricted |
| **Web scraping** | Firecrawl | Returns clean markdown |
| **Frontend framework** | React 18 + Vite 5 | Fast dev server, no bundler config |
| **Routing** | react-router-dom 6 | |
| **Styling** | TailwindCSS 3 (dark mode) | Custom palette: `primary` + `dark` |
| **HTTP client** | axios 1 | Interceptors for error logging |
| **Settings** | pydantic-settings 2 | Reads `.env`, `extra="ignore"` |
| **Logging** | stdlib `logging` | Named logger `fundflow` |

---

## 6. Setup Instructions

### Prerequisites

- Python 3.10+
- Node.js 18+
- A virtualenv (or use the included `backend/venv/`)

### Clone & enter

```bash
git clone <repo-url>
cd Pratik_Assignment
```

### Backend setup

```bash
cd backend
python -m venv venv             # or use the existing one
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # then fill in keys (see below)
python main.py
```

Backend runs at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Frontend setup

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:3000` (Vite proxies `/api` to backend).

---

## 7. Environment Variables

All variables live in `backend/.env` (copy from `backend/.env.example`).

### Required for any AI feature

| Variable | Description |
|---|---|
| `OPENROUTER_API_KEY` | OpenRouter API key. Get one at https://openrouter.ai. **Without this, cover-letter generation falls back to `null`.** |
| `OPENROUTER_BASE_URL` | OpenRouter API base. Default: `https://openrouter.ai/api/v1` |
| `OPENROUTER_MODEL` | Any currently-available model slug from https://openrouter.ai/models. Default: `anthropic/claude-3.5-sonnet` |

### Optional - enables live company discovery

| Variable | Description |
|---|---|
| `TAVILY_API_KEY` | Tavily search API key. **Without this, the orchestrator falls back to `backend/app/data/seed_companies.json`** (20 curated AI startups). |
| `FIRECRAWL_API_KEY` | Firecrawl scrape API key. Same fallback. |

### Tunable

| Variable | Default | Description |
|---|---|---|
| `DISCOVERY_CACHE_HOURS` | `24` | How long to reuse cached discovery results before re-running. |
| `ALLOWED_ORIGINS` | localhost:3000, 5173 | CORS allow-list. Add your production frontend in prod. |
| `DEBUG` | `true` | SQLAlchemy echo flag. Set to `false` in production. |

The frontend reads `VITE_API_BASE_URL` from `frontend/.env` (default `http://localhost:8000`).

---

## 8. Running the Backend

```bash
cd backend
source venv/bin/activate
python main.py
```

The server starts on port 8000 with hot reload (`--reload` is on). On startup it:
1. Initializes the SQLite database (creates tables if missing).
2. Mounts all five route modules.
3. Logs the OpenAI client init / failure path.

For production:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## 9. Running the Frontend

```bash
cd frontend
npm run dev      # dev server with HMR on port 3000
npm run build    # production bundle into dist/
npm run preview  # serve the built bundle locally
```

Vite is configured to proxy `/api` requests to `http://localhost:8000` (see `vite.config.js`), so the frontend can call `/api/workflow/weekly-report` without CORS in development.

---

## 10. Screenshots

Screenshots of the running demo are not committed to the repo (see `.gitignore`), but the demo flow is:

| Step | What happens |
|---|---|
| 1. Land on `/` | Hero copy explaining the six-stage pipeline |
| 2. Click "Get Started" | Routes to `/dashboard` |
| 3. Click "Generate Weekly Career Report" (no resume yet) | Shows the "Upload your resume" empty state |
| 4. Click "Upload Resume" → drag PDF | Uploads + AI-extracts rich profile |
| 5. Back to Dashboard → click "Generate" again | Runs 6 stages, shows loading workflow, then renders the report |
| 6. Click any company card | Routes to `/company/{name}` with the explainable AI report |
| 7. Click "Generate AI Cover Letter" | Shows real AI-drafted letter below the button |

---

## 11. AI Workflow Explanation

The orchestrator (`backend/app/services/orchestrator.py`) implements six sequential stages. All deterministic except `Stage 6` calling the LLM for cover letter generation.

```
Stage 1 - Resume Intelligence         (0.8s + 1.0s simulated)
  - Load latest resume from SQLite
  - Aggregate skills from analysis_json into a normalized list
  - Output: { name, summary, years, skills, technologies, ... }

Stage 2 - Market Intelligence          (1.2s simulated)
  - Load companies (cache → live discovery → seed fallback)
  - Compute funding-stage distribution, hiring signals, total funding
  - Output: market_summary, industry_breakdown

Stage 3 - Company Intelligence         (1.2s simulated)
  - For each company: score = 70 + 6 * (skill overlap count), capped at 98
  - Sort desc by score, take top 3
  - Output: top_matches array

Stage 4 - Career Intelligence          (1.0s simulated)
  - Count overlap by skill, by industry
  - Count missing skills by demand frequency
  - Output: career_intelligence, technology_breakdown,
            top_strengths, top_skill_gaps

Stage 5 - Opportunity Ranking          (no separate stage)
  - Already done in Stage 3

Stage 6 - Report Assembly               (0.8s + 1.0s simulated)
  - Generate cover letter for #1 match (real OpenRouter call)
  - Assemble final report payload
  - Output: full report object
```

The simulated delays (`time.sleep`) are purely UX — they make the workflow feel like a real AI agent thinking through steps rather than a function returning a payload. Total perceived time is ~6 seconds.

---

## 12. Future Improvements

| Idea | Notes |
|---|---|
| Real interview prep | Generate role-specific questions based on the candidate's resume + the company's actual tech stack |
| Multi-resume support | Let users upload several resumes and pick which one drives each report |
| Watchlist / pipeline | Star companies from Companies Explorer; track view history; show "Your Pipeline" panel |
| Time-series trend | Cache last N weekly reports; show match-score trend chart |
| Conversational Q&A | Add `/api/intelligence/ask` — user asks "why is PyTorch my top gap?" — deterministic answer from existing intelligence fields |
| Authentication | User accounts, multi-tenant |
| Production DB | PostgreSQL instead of SQLite |
| Background scheduler | APScheduler to refresh discovery nightly instead of waiting for first request |
| Vector search | Semantic company search by description embedding |
| PDF export | One-click download of full weekly report as styled PDF |

---

## 13. Known Limitations

- **First request is slow** when `DISCOVERY_CACHE_HOURS` expires: the orchestrator waits ~30 seconds for live Tavily + Firecrawl + OpenRouter normalization before returning. After the first call, subsequent calls are instant (cached).
- **Configurable OpenRouter model** must be a currently-available slug from https://openrouter.ai/models. Stale slugs return 404 and degrade gracefully to `cover_letter: null`.
- **No streaming**: the orchestrator returns the full report in one HTTP response. No SSE, no WebSocket.
- **Single-user**: no auth, no multi-tenancy. SQLite row = latest resume, no history.
- **Deterministic matching**: no embeddings, no vector DB, no semantic similarity. Skill-overlap is string-based (case-insensitive).
- **Resume parsing** is best-effort with scanned PDFs (PyMuPDF + pdfplumber). Heavily image-based or protected PDFs may fall back to the regex extractor.
- **Cover letter generation** depends on `OPENROUTER_API_KEY`. Without it, the dashboard still works fully — only the cover letter card is hidden.
- **Companies Explorer** shows the same dataset as the dashboard (cache or seed). With live discovery enabled, it's whatever the latest run surfaced.

---

Built with ❤️ as a 3-day internship MVP.