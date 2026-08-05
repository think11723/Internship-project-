# FundFlow AI

**AI Career Intelligence Platform** that turns a single resume upload into a personalized weekly briefing of funded AI startups — ranked, explained, and paired with a ready-to-send cover letter.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](#license)
[![Status: Production Ready](https://img.shields.io/badge/Status-Production%20Ready-brightgreen)](#)
[![Frontend: React + Vite](https://img.shields.io/badge/Frontend-React%20%2B%20Vite-blue)](#)
[![Backend: FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688)](#)

> **🚀 One resume upload → six-stage AI pipeline → personalized weekly briefing + cover letter**

---

## ✨ Features

| Stage | What it does |
|---|---|
| 📄 **Resume Upload** | Drag-drop or click to upload a PDF. 10 MB max, MIME-checked, sanitized filename. |
| 🤖 **Resume Intelligence** | AI extracts a 19-field rich profile (skills, technologies, recommended roles, experience, education). |
| 🔍 **Weekly Funding Agent** | Background scheduler scrapes the last 7 days of funded AI startups (Tavily + Firecrawl + OpenRouter) and rewrites the discovery cache. Falls back to curated seed if external services fail. |
| 🏢 **Company Discovery** | Live cache of recently funded AI startups with funding rounds, industry tags, headquarters, careers page. Falls back to a curated 20-company seed when the cache is unavailable. |
| 🎯 **AI Matching** | Deterministic overlap scoring per company — explains *why* a company matches. |
| 📊 **Weekly Career Report** | Six-stage orchestrator produces a complete dashboard: market intelligence, top opportunities, insights, career intelligence, cover letter. |
| ✍️ **AI Cover Letter** | One-click personalized cover letter for the top match — written in the candidate's voice. |
| 💾 **Session Persistence** | Report survives navigation and hard refresh via `sessionStorage`. No backend roundtrip. |
| 👤 **Resume Management** | View, Replace, Delete the active resume with confirmations and full state reset. |
| 📈 **Real Upload Progress** | 9-stage pipeline indicator with byte-level upload progress and per-stage server feedback. |
| 🛡️ **CORS** | Configured for `localhost:3000`–`3010` and `5173` by default. |
| ⚠️ **Friendly Errors** | Standardized error envelope `{status, message, error_code, request_id}` with `request_id` for support correlation. |
| ♿ **Accessibility** | Skip-link, focus rings, `aria-current`, `role="status"`, `prefers-reduced-motion` support. |

---

## 📸 Screenshots

> Placeholder — drop your real screenshots here.

| Landing | Dashboard | Company Details |
|---|---|---|
| _Screenshot placeholder_ | _Screenshot placeholder_ | _Screenshot placeholder_ |

---

## 🏛️ Architecture

```
┌────────────────────────┐         ┌────────────────────────┐
│  Browser (React 18)    │         │  FastAPI (Python 3.11)  │
│  Vite + Tailwind         │  HTTPS  │  SQLAlchemy + SQLite     │
│  Axios + Context         │ ──────► │  PyMuPDF + pdfplumber    │
│  sessionStorage          │         │  OpenRouter (LLM)        │
│                         │         │  Tavily + Firecrawl      │
└────────────────────────┘         └────────────────────────┘
                                          │
                                          ▼
                                ┌──────────────────────┐
                                │  SQLite (fundflow.db) │
                                │  uploads/ (PDF temp)  │
                                │  cache/ (discovery)  │
                                └──────────────────────┘
```

**Pipeline (per `POST /api/workflow/weekly-report`):**

1. **Resume Intelligence** — load latest `Resume` row → build candidate profile
2. **Market Intelligence** — aggregate company dataset stats (industries, funding, hiring signals)
3. **Company Intelligence** — score top 3 by skill overlap (deterministic)
4. **Career Intelligence** — top hiring industries, dominant technologies, skill gaps
5. **Opportunity Ranking** — re-uses Stage 3 output
6. **Report Assembly** — generate cover letter for #1 match, return full payload

---

## 🛠️ Tech Stack

**Frontend**
- React 18 + Vite 5
- React Router 6
- TailwindCSS 3 (custom Pipeup palette)
- Axios 1

**Backend**
- FastAPI 0.104
- SQLAlchemy 2
- SQLite (single-user, persistent volume in prod)
- PyMuPDF + pdfplumber (PDF text extraction)
- `openai` 1.x SDK (OpenRouter-compatible)
- Pydantic 2

**External Services**
- [OpenRouter](https://openrouter.ai) — LLM gateway
- [Tavily](https://tavily.com) — web search (optional, for live discovery)
- [Firecrawl](https://firecrawl.com) — web scraping (optional, for live discovery)

---

## 📦 Installation

### Prerequisites
- Python **3.11+**
- Node.js **18+**, npm **9+**
- Git

### Clone

```bash
git clone https://github.com/your-org/fundflow-ai.git
cd fundflow-ai
```

### Backend

```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
# Edit .env and fill in OPENROUTER_API_KEY (required), TAVILY/FIRECRAWL (optional)
python main.py
```

Backend serves on `http://localhost:8000`. Interactive API docs at `http://localhost:8000/docs`.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
# (defaults to Vite proxy — no env edit required for local dev)
npm run dev
```

Frontend serves on `http://localhost:3000`. The Vite dev server proxies `/api/*` to the backend.

---

## 🔐 Environment Variables

### `backend/.env`

| Var | Required | Description | Default |
|---|---|---|---|
| `OPENROUTER_API_KEY` | ✅ | OpenRouter API key (`sk-or-v1-…`) | — |
| `OPENROUTER_BASE_URL` | ✅ | OpenRouter base URL | `https://openrouter.ai/api/v1` |
| `OPENROUTER_MODEL` | ✅ | Any OpenRouter-supported model slug | `anthropic/claude-3.5-sonnet` |
| `DATABASE_URL` | ✅ | SQLAlchemy URL | `sqlite:///./fundflow.db` |
| `TAVILY_API_KEY` | ❌ | Tavily key (live company discovery) | empty → uses seed |
| `FIRECRAWL_API_KEY` | ❌ | Firecrawl key (live company scraping) | empty → uses seed |
| `DISCOVERY_CACHE_HOURS` | ❌ | Cache TTL | `24` |
| `WEEKLY_AGENT_ENABLED` | ❌ | Master switch for the weekly background scheduler | `true` |
| `WEEKLY_AGENT_INTERVAL_HOURS` | ❌ | How often the agent runs (background thread) | `168` (7 days) |
| `WEEKLY_AGENT_LOOKBACK_DAYS` | ❌ | Tavily date-window size | `7` |
| `WEEKLY_AGENT_RUN_ONCE` | ❌ | Run once on startup then exit (intended for CI) | `false` |
| `ALLOWED_ORIGINS` | ❌ | CORS allow-list (JSON array) | localhost 3000–3010, 5173 |
| `ENVIRONMENT` | ❌ | `development` / `production` | `development` |
| `DEBUG` | ❌ | SQL echo, verbose logs | `false` |
| `LLM_PROVIDER` | ❌ | Future multi-provider | `openrouter` |

### `frontend/.env`

| Var | Required | Description | Default |
|---|---|---|---|
| `VITE_API_BASE_URL` | ❌ | Backend URL in production | empty → Vite proxy |

---

## 🏃 Run Locally

```bash
# Terminal 1 — backend on :8000
cd backend && source venv/bin/activate && python main.py

# Terminal 2 — frontend on :3000
cd frontend && npm run dev
```

Open <http://localhost:3000>. The Landing page greets you, and the **Generate my weekly report** button takes you to the Dashboard.

---

## 🚀 Deployment

See **[DEPLOYMENT.md](DEPLOYMENT.md)** for the full deployment guide covering Vercel, Render, Railway, and Docker.

Quick links:
- [Frontend on Vercel](DEPLOYMENT.md#frontend-on-vercel)
- [Backend on Render](DEPLOYMENT.md#backend-on-render)
- [Backend on Railway](DEPLOYMENT.md#backend-on-railway)
- [Full Docker setup](DEPLOYMENT.md#docker)

---

## 📁 Folder Structure

```
fundflow-ai/
├── backend/
│   ├── .env.example
│   ├── Dockerfile
│   ├── main.py                 # FastAPI app factory
│   ├── requirements.txt
│   ├── app/
│   │   ├── api/routes/        # health, resume, companies, documents, workflow
│   │   ├── core/              # config, logging, exceptions, middleware
│   │   ├── data/              # seed_companies.json (20 AI startups)
│   │   ├── db/                # SQLAlchemy session
│   │   ├── models/            # Resume ORM model
│   │   ├── schemas/           # Pydantic response models
│   │   ├── services/          # orchestrator, resume, generation, llm, intelligence
│   │   └── tools/             # PDF parser
│   ├── cache/                 # discovery cache (gitignored)
│   └── uploads/               # PDF temp storage (gitignored)
├── frontend/
│   ├── .env.example
│   ├── index.html
│   ├── package.json
│   ├── postcss.config.js
│   ├── tailwind.config.js
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx
│       ├── main.jsx
│       ├── index.css
│       ├── components/        # Badge, Button, Card, CoverLetterCard, …
│       ├── context/           # ReportContext, ResumeContext
│       ├── layouts/           # Layout.jsx
│       ├── pages/             # Landing, Dashboard, ResumeUpload, Companies, CompanyDetails
│       └── services/          # api, company, generation, resume, workflow
├── .gitignore                 # root ignore
├── DEPLOYMENT.md              # full deployment guide
├── LICENSE                     # MIT
└── README.md                  # you are here
```

---

## 🔌 API Overview

Interactive docs: **`/docs`** (Swagger UI) on the backend.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Liveness probe |
| `POST` | `/api/resume/upload` | Upload a PDF resume → 19-field AI extraction |
| `GET` | `/api/resume/latest` | Metadata for the "Current Resume" card |
| `GET` | `/api/resume/latest/analysis` | Full analysis for the "View Resume" modal |
| `DELETE` | `/api/resume/latest` | Delete the active resume + reset all derived state |
| `GET` | `/api/resume/upload-status/{job_id}` | Poll real-time stage updates (used by upload progress UI) |
| `GET` | `/api/companies` | Companies list, with filters, sort, pagination |
| `POST` | `/api/companies/discover` | Force a live discovery run (Tavily + Firecrawl) |
| `POST` | `/api/companies/match` | Match companies against a candidate profile |
| `GET` | `/api/companies/{name}` | Company detail + deterministic match vs latest resume |
| `POST` | `/api/documents/generate` | Generate a personalized cover letter |
| `POST` | `/api/workflow/weekly-report` | Run the 6-stage orchestrator and return the full report |

### Error envelope

All errors return:

```json
{
  "status": "error",
  "message": "Human-readable explanation of what went wrong.",
  "error_code": "HTTP_500",
  "timestamp": "2026-08-05T08:35:21.123Z",
  "request_id": "9b399b52-4239-4544-979f-d3dd0f810e4c"
}
```

Use the `request_id` when reporting issues — it's searchable in the server logs.

---

## ⚠️ Known Limitations

- **OpenRouter free tier** is rate-limited (50 requests/day). The cover-letter endpoint will return `503` once exhausted. Upgrade OpenRouter for production volume.
- **SQLite is single-process**. Suitable for a single-user demo. For multi-worker deployments, switch to PostgreSQL (no schema changes required).
- **No auth.** Anyone with the URL can use the app. Deploy behind a VPN / OAuth proxy if you need access control.
- **No rate limiting.** A determined client can drive up your OpenRouter bill. Add a rate limiter (e.g. `slowapi`) if exposed publicly.
- **Tavily / Firecrawl keys are optional.** Without them, the orchestrator falls back to the curated seed of 20 AI startups in `backend/app/data/seed_companies.json`.
- **OpenRouter model is configurable** but the prompt is tuned for Claude-class models. Smaller models may produce lower-quality cover letters.

---

## 🛣️ Roadmap

- [ ] **PostgreSQL migration** with Alembic
- [ ] **OAuth / Auth** (GitHub, Google) with per-user report history
- [ ] **Resume history** (keep N previous uploads, pick which drives the report)
- [ ] **Live company discovery** dashboard (real-time Tavily + Firecrawl cron)
- [ ] **Streaming cover letter** (token-by-token via SSE)
- [ ] **Multi-language support** (en, es, fr, de, ja)
- [ ] **Watchlist** — star companies, track status over time
- [ ] **Interview prep** — generate role-specific Q&A from the matched company

---

## 🤝 Credits

- **UI inspiration** — [Pipeup](https://pipeup.in) (editorial minimal aesthetic)
- **LLM** — [Anthropic Claude](https://www.anthropic.com) via [OpenRouter](https://openrouter.ai)
- **Discovery stack** — [Tavily](https://tavily.com), [Firecrawl](https://firecrawl.com)
- **PDF parsing** — [PyMuPDF](https://pymupdf.readthedocs.io), [pdfplumber](https://github.com/jsvine/pdfplumber)

---

## 📄 License

This project is licensed under the **MIT License** — see [LICENSE](LICENSE) for the full text.

```
MIT License

Copyright (c) 2026 FundFlow AI contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
```

---

<div align="center">

**[⬆ Back to top](#fundflow-ai)** · Made with 🟢 by humans who like their cover letters AI-generated

</div>
