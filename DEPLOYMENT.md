# Deployment Guide

This document covers how to deploy FundFlow AI to production. The application is split into a **frontend** (static React build) and a **backend** (long-running FastAPI process). They are deployed independently.

---

## Table of Contents

1. [Architecture overview](#architecture-overview)
2. [Prerequisites](#prerequisites)
3. [Environment variables](#environment-variables)
4. [Frontend on Vercel](#frontend-on-vercel)
5. [Frontend on Netlify](#frontend-on-netlify)
6. [Backend on Render](#backend-on-render)
7. [Backend on Railway](#backend-on-railway)
8. [Docker](#docker)
9. [Persistent storage](#persistent-storage)
10. [Common deployment issues](#common-deployment-issues)
11. [Production checklist](#production-checklist)

---

## Architecture overview

```
                  ┌──────────────────────┐
   Browser ─────► │  Vercel / Netlify    │  Static SPA (React + Vite)
                  │  https://app.example  │
                  └──────────┬───────────┘
                             │ HTTPS / JSON
                             ▼
                  ┌──────────────────────┐
                  │  Render / Railway     │  FastAPI + uvicorn
                  │  https://api.example   │
                  │  Single process        │  (or Docker)
                  └──────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │  OpenRouter / Tavily  │  External SaaS
                  │  Firecrawl            │
                  └──────────────────────┘

                  ┌──────────────────────┐
                  │  Persistent Volume    │
                  │  fundflow.db (SQLite) │
                  │  uploads/ (PDFs)      │
                  │  cache/ (discovery)   │
                  └──────────────────────┘
```

---

## Prerequisites

- **Frontend** — a static-hosting service (Vercel or Netlify).
- **Backend** — a Python host (Render, Railway, Fly.io, or a Docker host).
- **Persistent storage** — a volume that survives restarts (Render disks, Railway volumes, or Docker volume).
- **OpenRouter API key** — required. Get one at <https://openrouter.ai>.
- *(Optional)* **Tavily** + **Firecrawl** keys for live company discovery. Without them, the curated 20-company seed is used.

---

## Environment variables

### Frontend (`frontend/.env`)

| Var | Required | Description |
|---|---|---|
| `VITE_API_BASE_URL` | ✅ in prod | Full backend URL, e.g. `https://api.fundflow.example` |

### Backend (`backend/.env`)

See the full table in [README.md > Environment variables](README.md#-environment-variables). The minimum required set is:

```
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet
DATABASE_URL=sqlite:///./fundflow.db
ALLOWED_ORIGINS=["https://app.fundflow.example"]
ENVIRONMENT=production
DEBUG=false
```

> **🔐 Security:** never commit `.env`. The included `.gitignore` excludes it. Rotate keys immediately if they leak into chat history or version control.

---

## Frontend on Vercel

1. **Sign in** to <https://vercel.com> and click **Add New → Project**.
2. **Import** the Git repository.
3. Configure:
   - **Root Directory:** `frontend`
   - **Build Command:** `npm run build`
   - **Output Directory:** `dist`
   - **Install Command:** `npm install`
4. Add environment variable:
   - `VITE_API_BASE_URL` = `https://api.fundflow.example`
5. Click **Deploy**.

Vercel auto-detects Vite, sets the correct Node version, and serves the SPA with proper SPA fallback routing. Subsequent pushes to `main` auto-deploy.

---

## Frontend on Netlify

1. **Sign in** to <https://netlify.com> and click **Add new site → Import an existing project**.
2. Connect the GitHub repo.
3. Configure:
   - **Base directory:** `frontend`
   - **Build command:** `npm run build`
   - **Publish directory:** `frontend/dist`
4. Add environment variable:
   - `VITE_API_BASE_URL` = `https://api.fundflow.example`
5. Click **Deploy site**.

For SPA routing (so direct URL loads work), add a `_redirects` file in `frontend/public/`:

```
/*    /index.html   200
```

---

## Backend on Render

1. **Sign in** to <https://render.com> and click **New → Web Service**.
2. Connect the GitHub repo.
3. Configure:
   - **Root Directory:** `backend`
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Plan:** Starter (or higher for production)
4. Add environment variables (see [Environment variables](#environment-variables) above).
5. **Add a persistent disk**:
   - In the dashboard, go to **Disks → Add Disk**.
   - **Name:** `fundflow-data`
   - **Mount Path:** `/data`
   - **Size:** 1 GB (enough for hundreds of resumes)
6. Update `DATABASE_URL` to use the mount path:
   ```
   DATABASE_URL=sqlite:////data/fundflow.db
   ```
7. Update `main.py` (or via env override) so `uploads/` and `cache/` resolve under `/data`:
   - Set `FUNDFLOW_DATA_DIR=/data` in environment.
   - In `backend/main.py` (or a small startup helper), set:
     ```python
     import os
     os.makedirs(os.environ.get("FUNDFLOW_DATA_DIR", "."), exist_ok=True)
     UPLOAD_DIR = Path(os.environ["FUNDFLOW_DATA_DIR"]) / "uploads"
     CACHE_DIR  = Path(os.environ["FUNDFLOW_DATA_DIR"]) / "cache"
     ```
8. Click **Create Web Service**.

### Health check

Render will hit `/api/health` automatically. The endpoint returns `{"status":"healthy"}` with `200`.

---

## Backend on Railway

1. **Sign in** to <https://railway.app> and click **New Project → Deploy from GitHub**.
2. Select the repository, click **Add variables**:
   - All env vars from the table above.
3. In **Settings → Deploy**:
   - **Root Directory:** `backend`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add a **Volume** at `/data` (1 GB).
5. Update `DATABASE_URL` and `FUNDFLOW_DATA_DIR` as in the Render section.

Railway auto-assigns a domain (`https://fundflow-ai.up.railway.app`). Add a custom domain in **Settings → Networking**.

---

## Docker

A `Dockerfile` is included in `backend/`. Build and run locally:

```bash
cd backend
docker build -t fundflow-backend .
docker run -p 8000:8000 \
  -e OPENROUTER_API_KEY=sk-or-v1-... \
  -e OPENROUTER_BASE_URL=https://openrouter.ai/api/v1 \
  -e OPENROUTER_MODEL=anthropic/claude-3.5-sonnet \
  -e DATABASE_URL=sqlite:////data/fundflow.db \
  -e ALLOWED_ORIGINS='["https://app.fundflow.example"]' \
  -e ENVIRONMENT=production \
  -e DEBUG=false \
  -v fundflow-data:/data \
  fundflow-backend
```

For **Docker Compose** (backend + reverse proxy), see [`docker-compose.yml`](docker-compose.yml) example below.

```yaml
version: '3.8'
services:
  backend:
    build: ./backend
    restart: always
    environment:
      OPENROUTER_API_KEY: ${OPENROUTER_API_KEY}
      OPENROUTER_BASE_URL: https://openrouter.ai/api/v1
      OPENROUTER_MODEL: anthropic/claude-3.5-sonnet
      DATABASE_URL: sqlite:////data/fundflow.db
      ALLOWED_ORIGINS: '["https://app.fundflow.example"]'
      ENVIRONMENT: production
      DEBUG: 'false'
    volumes:
      - fundflow-data:/data
    healthcheck:
      test: ['CMD', 'curl', '-f', 'http://localhost:8000/api/health']
      interval: 30s
      timeout: 5s
      retries: 3

  nginx:
    image: nginx:alpine
    ports:
      - '80:443'
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./certs:/etc/nginx/certs:ro
    depends_on:
      - backend

volumes:
  fundflow-data:
```

---

## Persistent storage

The backend writes three things to disk:

| Path | Contents | Volatile? |
|---|---|---|
| `fundflow.db` (SQLite) | Resume rows, parsed profiles | Must persist |
| `uploads/{uuid}.pdf` | Temporary PDFs during upload | Auto-deleted after processing — no persistence needed |
| `cache/latest_discovery.json` | Company discovery cache | Should persist across restarts |

Configure a persistent volume at `/data` on your host, then set:

```bash
DATABASE_URL=sqlite:////data/fundflow.db
FUNDFLOW_DATA_DIR=/data
```

(Requires updating the path constants in `backend/app/api/routes/resume.py` and `backend/app/services/orchestrator.py` to read from `FUNDFLOW_DATA_DIR` — see the Render section above for the small startup helper.)

---

## Common deployment issues

### 🔴 CORS error: "No 'Access-Control-Allow-Origin' header"

The browser blocks the request because the backend's `ALLOWED_ORIGINS` does not include the frontend URL.

**Fix:** set `ALLOWED_ORIGINS` in the backend `.env` to a JSON array containing the frontend's full origin:

```bash
ALLOWED_ORIGINS=["https://app.fundflow.example","https://www.fundflow.example"]
```

Restart the backend. The error message from the browser dev tools will show the exact origin that was rejected.

### 🔴 503 "Cover letter generation is temporarily unavailable"

OpenRouter rate limit hit. Either upgrade your OpenRouter tier or wait for the daily reset. The error envelope includes a `request_id` for support.

### 🔴 First request takes ~30 s

This is the discovery cache being populated on first request. The orchestrator pre-warms the cache at startup, so this should only happen on a cold start with no cache. Check the startup logs for `Pre-warmed discovery cache with N companies`.

If pre-warm is not running, ensure `backend/main.py` is using the `@app.on_event("startup")` handler and that the deployment is single-process (some PaaS force single worker by default).

### 🔴 "Something went wrong on our end" — 500s

Check the backend logs for the `request_id` shown in the error response. Common causes:

- Missing API key — backend logs `ValueError("OPENROUTER_API_KEY not configured")` at startup.
- Bad `OPENROUTER_MODEL` — backend logs `404 not found` from the LLM gateway.
- SQLite `database is locked` — multiple workers writing simultaneously. Run with `--workers 1` (default for `uvicorn`).

### 🔴 Files disappear on restart

Persistent volume not configured. See the [Persistent storage](#persistent-storage) section.

### 🔴 LLM rate limit hit in the first hour

Free OpenRouter tier is **50 requests/day**. The cover-letter endpoint is the slowest. Either:

- Upgrade at <https://openrouter.ai/account>
- Use a paid model (`OPENROUTER_MODEL=anthropic/claude-3-haiku`)
- Add a rate limiter (e.g. `slowapi`) before exposing publicly

---

## Production checklist

Before going live, verify **every** item:

- [ ] All `OPENROUTER_API_KEY`, `TAVILY_API_KEY`, `FIRECRAWL_API_KEY` are set in the host's secret manager (not committed to git).
- [ ] `ALLOWED_ORIGINS` includes the **exact** frontend origin (including protocol and port).
- [ ] `ENVIRONMENT=production` and `DEBUG=false`.
- [ ] Persistent volume mounted at `/data` (or equivalent) and `DATABASE_URL` uses that path.
- [ ] `curl https://api.fundflow.example/api/health` returns 200 with `{"status":"healthy"}`.
- [ ] `curl https://api.fundflow.example/docs` returns Swagger UI.
- [ ] Frontend deployed and loads with no console errors.
- [ ] End-to-end: upload a real PDF on the production frontend → report renders within ~30 s.
- [ ] Logs streaming to a log aggregator (Render/Railway do this automatically).
- [ ] No 500s in logs for 10 minutes of typical use.
- [ ] DNS configured (custom domain, A record or CNAME to the host's domain).
- [ ] TLS certificate valid (Vercel/Render/Railway provide Let's Encrypt automatically).
- [ ] `git log` shows no `.env` files ever committed.
- [ ] OpenRouter usage dashboard shows your traffic.

---

## After deployment

- Monitor OpenRouter usage at <https://openrouter.ai/activity>.
- Back up `fundflow.db` nightly (Render and Railway both have snapshot tools; on Docker, `docker exec fundflow-backend sqlite3 /data/fundflow.db ".backup /data/backups/db-$(date +%F).sqlite"`).
- Watch the `request_id`s in the error envelopes — they're the fastest way to find the exact log line.
