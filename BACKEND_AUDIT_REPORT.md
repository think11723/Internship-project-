# FundFlow AI Backend Audit Report

**Audit Date:** 2025-01-21
**Auditor:** Principal Backend Architect
**Scope:** Complete backend architecture, implementation, and technical debt analysis

---

## STEP 1: PROJECT STRUCTURE

```
backend/
├── main.py                          # FastAPI entry point
├── requirements.txt                 # Python dependencies
├── .env.example                     # Environment template
├── .gitignore
├── app/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── health.py           # Health check endpoint
│   │       ├── resume.py           # Resume upload endpoint
│   │       ├── companies.py        # Company listing & matching
│   │       ├── documents.py        # Cover letter generation
│   │       └── workflow.py         # Weekly report orchestration
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py              # Pydantic settings
│   │   └── logging.py             # Logging configuration
│   ├── db/
│   │   ├── __init__.py
│   │   └── session.py             # SQLAlchemy session
│   ├── models/
│   │   ├── __init__.py
│   │   └── resume.py              # Resume ORM model
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── resume.py              # Pydantic schemas
│   ├── services/
│   │   ├── __init__.py
│   │   ├── resume_service.py      # Resume parsing & AI extraction
│   │   ├── llm_service.py         # OpenRouter integration
│   │   ├── discovery_service.py   # Tavily + Firecrawl + OpenAI discovery
│   │   ├── generation_service.py  # Cover letter generation
│   │   ├── intelligence.py        # Market & career intelligence
│   │   └── orchestrator.py        # Weekly report orchestration
│   ├── tools/
│   │   ├── __init__.py
│   │   └── document_parser.py    # PDF text extraction
│   └── data/
│       └── seed_companies.json    # Demo data (20 companies)
```

**Assessment:** Clean, well-organized FastAPI structure. Clear separation of concerns with services, routes, models, schemas, and tools.

---

## STEP 2: ENDPOINT AUDIT

| Endpoint | Method | Purpose | Status | Working? | Controller | Service Used | External APIs | Current Problems |
|----------|--------|---------|--------|----------|------------|--------------|---------------|-----------------|
| `/api/health` | GET | Health check | IMPLEMENTED | YES | health.py | None | None | None |
| `/api/resume/upload` | POST | Upload & parse resume | IMPLEMENTED | YES | resume.py | ResumeIntelligenceService | OpenRouter (via LLMService) | None |
| `/api/companies` | GET | List companies with scoring | IMPLEMENTED | YES | companies.py | orchestrator helpers | None | None |
| `/api/companies/discover` | POST | Discover new companies | STUB | NO | companies.py | None | None | NOT IMPLEMENTED - returns 501 |
| `/api/companies/match` | POST | Match companies | STUB | NO | companies.py | None | None | NOT IMPLEMENTED - returns 501 |
| `/api/documents/generate` | POST | Generate cover letter | IMPLEMENTED | YES | documents.py | generation_service | OpenRouter (via LLMService) | None |
| `/api/workflow/weekly-report` | POST | Generate weekly report | IMPLEMENTED | YES | workflow.py | orchestrator | OpenRouter, Tavily, Firecrawl, OpenAI | Uses simulated delays |

**Summary:** 7 endpoints total. 5 working, 2 stubs (discover, match). All working endpoints use real AI integrations.

---

## STEP 3: SERVICE AUDIT

### resume_service.py
- **Purpose:** Extract structured profile from PDF resumes
- **Implemented:** YES
- **Working:** YES
- **Stub:** NO
- **Mock:** NO (has local regex fallback if AI fails)
- **Dependencies:** PDFParser (PyMuPDF + pdfplumber), LLMService (OpenRouter)
- **Exceptions:** ValueError (no text), JSON decode errors (retries once)
- **TODOs:** None
- **Fallback:** Local regex/keyword extractor if LLM fails

### llm_service.py
- **Purpose:** OpenRouter integration for LLM calls
- **Implemented:** YES
- **Working:** YES (requires OPENROUTER_API_KEY)
- **Stub:** NO
- **Mock:** NO
- **Dependencies:** OpenAI SDK, httpx
- **Exceptions:** ValueError (missing API key), network errors
- **TODOs:** None
- **API Key Required:** YES (OPENROUTER_API_KEY)
- **Fallback:** None (fails gracefully)

### discovery_service.py
- **Purpose:** Real-time company discovery via Tavily + Firecrawl + OpenAI
- **Implemented:** YES
- **Working:** YES (requires TAVILY_API_KEY and FIRECRAWL_API_KEY)
- **Stub:** NO
- **Mock:** NO
- **Dependencies:** Tavily API, Firecrawl API, LLMService (OpenAI via OpenRouter)
- **Exceptions:** ValueError (missing keys), network errors, empty results
- **TODOs:** None
- **API Keys Required:** TAVILY_API_KEY, FIRECRAWL_API_KEY
- **Fallback:** Returns error (caller falls back to seed data)

### generation_service.py
- **Purpose:** Cover letter generation
- **Implemented:** YES
- **Working:** YES (requires OPENROUTER_API_KEY)
- **Stub:** NO
- **Mock:** NO
- **Dependencies:** LLMService
- **Exceptions:** Network errors, empty content
- **TODOs:** None
- **Fallback:** Returns None on failure

### intelligence.py
- **Purpose:** Market and career intelligence aggregation
- **Implemented:** YES
- **Working:** YES
- **Stub:** NO
- **Mock:** NO
- **Dependencies:** None (deterministic calculations)
- **Exceptions:** None
- **TODOs:** None
- **Fallback:** None

### orchestrator.py
- **Purpose:** Weekly report workflow orchestration
- **Implemented:** YES
- **Working:** YES
- **Stub:** NO (uses simulated delays via time.sleep)
- **Mock:** NO (delays are simulated but data is real)
- **Dependencies:** discovery_service, generation_service, intelligence, llm_service
- **Exceptions:** None (falls back to seed data on discovery failure)
- **TODOs:** 1 comment about replacing simulated delays with real AI work
- **Fallback:** Seed data (seed_companies.json) if discovery fails

---

## STEP 4: DATABASE AUDIT

### Database: SQLite (fundflow.db)

**Collections/Tables:**
- `resumes` - Single table for storing parsed resume data

**Schema (resumes table):**
- `id` (Integer, PK, autoincrement)
- `original_filename` (String 255)
- `file_path` (String 500, nullable)
- `name` (String 255, nullable)
- `email` (String 255, nullable)
- `phone` (String 50, nullable)
- `location` (String 255, nullable)
- `summary` (Text, nullable)
- `skills` (JSON, nullable)
- `experience` (JSON, nullable)
- `education` (JSON, nullable)
- `projects` (JSON, nullable)
- `certifications` (JSON, nullable)
- `technologies` (JSON, nullable)
- `strengths` (JSON, nullable)
- `analysis_json` (JSON, nullable) - Full AI-extracted profile
- `raw_text` (Text, nullable)
- `parsed_at` (DateTime, timezone=True)

**Relationships:** None (single table)

**Indexes:** Primary key index on `id`

**Validation:** Pydantic schemas at API level, database-level minimal

**Current Status:** WORKING, minimal schema sufficient for current use case

**Missing:**
- No companies table (companies are stored in JSON file or cache)
- No users table (no authentication)
- No sessions table
- No audit logging table

---

## STEP 5: WORKFLOW AUDIT

### Resume Upload
- **Implemented:** YES
- **Working:** YES
- **Uses AI:** YES (OpenRouter via LLMService)
- **Returns Mock Data:** NO (real AI extraction)
- **Broken:** NO
- **Fallback:** Local regex/keyword extractor if AI fails

### Resume Parsing
- **Implemented:** YES
- **Working:** YES
- **Uses AI:** YES (OpenRouter)
- **Returns Mock Data:** NO
- **Broken:** NO
- **Fallback:** Regex extractor if JSON parse fails

### Skill Extraction
- **Implemented:** YES
- **Working:** YES
- **Uses AI:** YES (OpenRouter)
- **Returns Mock Data:** NO
- **Broken:** NO
- **Fallback:** Regex extractor

### Company Search/Discovery
- **Implemented:** YES
- **Working:** YES (with API keys, falls back to seed)
- **Uses AI:** YES (Tavily + Firecrawl + OpenAI)
- **Returns Mock Data:** NO (seed data is real curated data)
- **Broken:** NO (graceful fallback to seed)
- **Fallback:** seed_companies.json (20 companies)

### Company Matching
- **Implemented:** YES
- **Working:** YES
- **Uses AI:** NO (deterministic skill overlap)
- **Returns Mock Data:** NO
- **Broken:** NO
- **Algorithm:** Score = 70 + (overlap_count * 6), capped at 98

### Ranking
- **Implemented:** YES
- **Working:** YES
- **Uses AI:** NO (deterministic)
- **Returns Mock Data:** NO
- **Broken:** NO
- **Algorithm:** Sort by score descending, then alphabetical

### Skill Gap Analysis
- **Implemented:** YES
- **Working:** YES
- **Uses AI:** NO (deterministic)
- **Returns Mock Data:** NO
- **Broken:** NO
- **Algorithm:** Set difference between company skills and candidate skills

### Weekly Report
- **Implemented:** YES
- **Working:** YES
- **Uses AI:** YES (OpenRouter for cover letter, OpenAI for discovery normalization)
- **Returns Mock Data:** NO (uses real resume + real/seed companies)
- **Broken:** NO
- **Delays:** Simulated (time.sleep) - NOT real AI work

### Cover Letter
- **Implemented:** YES
- **Working:** YES (with API key)
- **Uses AI:** YES (OpenRouter)
- **Returns Mock Data:** NO
- **Broken:** NO
- **Fallback:** Returns None on failure

---

## STEP 6: AI AUDIT

### OpenRouter (via LLMService)
- **Working:** YES (requires OPENROUTER_API_KEY)
- **API Key Required:** YES
- **Fallback:** NO (fails gracefully)
- **Errors:** Logged, returns None or raises
- **Missing:** NO (configured in settings)
- **Model:** anthropic/claude-3.5-sonnet (configurable)
- **Uses:**
  - Resume extraction (JSON mode)
  - Cover letter generation

### OpenAI (via discovery_service)
- **Working:** YES (requires OPENAI_API_KEY)
- **API Key Required:** YES
- **Fallback:** NO (discovery fails, falls back to seed)
- **Errors:** Logged, raises exception
- **Missing:** Configured but optional (only used in discovery)
- **Model:** gpt-4.1-mini (hardcoded)
- **Uses:**
  - Company normalization from scraped content

### Tavily (via discovery_service)
- **Working:** YES (requires TAVILY_API_KEY)
- **API Key Required:** YES
- **Fallback:** NO (discovery fails, falls back to seed)
- **Errors:** Logged, returns empty results
- **Missing:** Configured but optional
- **Uses:**
  - Web search for funded AI startups

### Firecrawl (via discovery_service)
- **Working:** YES (requires FIRECRAWL_API_KEY)
- **API Key Required:** YES
- **Fallback:** NO (discovery fails, falls back to seed)
- **Errors:** Logged, returns empty results
- **Missing:** Configured but optional
- **Uses:**
  - Web scraping of discovered URLs

### Embeddings
- **Implemented:** NO
- **Working:** N/A
- **Missing:** YES

### Prompt Files
- **Location:** Inline in service files (not separate files)
- **Resume extraction prompt:** In resume_service.py (line 26-70)
- **Cover letter prompt:** In llm_service.py (line 96-144)
- **Discovery normalization prompt:** In discovery_service.py (line 177-190)
- **Status:** Working, no external prompt files

---

## STEP 7: COMPANY DATASET

### Company Source
- **Primary:** seed_companies.json (20 curated companies)
- **Secondary:** Live discovery (Tavily + Firecrawl + OpenAI)
- **Fallback:** Seed data if discovery fails

### Static JSON?
- **YES** - seed_companies.json contains 20 real AI startups
- **Quality:** High - real companies with accurate data
- **Size:** 20 companies

### Database?
- **NO** - Companies are not stored in database
- **Storage:** JSON file + file-based cache

### Firecrawl?
- **YES** - Used in live discovery pipeline
- **Required:** FIRECRAWL_API_KEY
- **Fallback:** Seed data

### API?
- **YES** - Uses Tavily for search, Firecrawl for scraping
- **Fallback:** Seed data

### Cached?
- **YES** - File-based cache (cache/latest_discovery.json)
- **TTL:** 24 hours (configurable via DISCOVERY_CACHE_HOURS)
- **Pre-warming:** Yes on startup (background thread)

### Fresh?
- **Cache:** 24-hour TTL
- **Live discovery:** Real-time when cache is stale
- **Seed data:** Static (manual update needed)

### How Many Companies?
- **Seed:** 20 companies
- **Discovery:** Up to 20 (MAX_FINAL_COMPANIES)
- **Total:** 20-40 depending on cache state

### Filtering?
- **API:** Not implemented (discover/match endpoints are stubs)
- **Frontend:** Client-side filtering on full dataset

### Sorting?
- **API:** Not implemented
- **Frontend:** Client-side sorting
- **Ranking:** Deterministic scoring in orchestrator

### Pagination?
- **Not implemented**
- **Returns:** Full dataset (20-40 companies)

---

## STEP 8: MATCHING ENGINE

### How Score is Calculated
**Formula:** `score = min(98, 70 + (overlap_count * 6))`

**Logic:**
1. Extract company skills → lowercase set
2. Extract candidate skills → lowercase set
3. Calculate intersection (overlap)
4. Each overlapping skill adds 6 points
5. Base score is 70
6. Capped at 98

**Example:**
- 0 overlapping skills → score = 70
- 3 overlapping skills → score = 88
- 5 overlapping skills → score = 100 (capped at 98)

### Deterministic?
- **YES** - No AI, no randomness
- Same input always produces same output

### AI-Generated?
- **NO** - Pure deterministic algorithm

### Fake?
- **NO** - Real skill overlap calculation

### Weighted?
- **YES** - Each skill has equal weight (6 points)
- No prioritization of certain skills

### Skill Overlap Exists?
- **YES** - Case-insensitive intersection of skill sets

### Experience Matters?
- **NO** - Experience duration not factored into score
- Experience is stored but not used in matching

### Education Matters?
- **NO** - Education not factored into score
- Education is stored but not used in matching

### Keywords Only?
- **YES** - Matching is purely keyword-based skill overlap
- No semantic understanding
- No context matching

---

## STEP 9: WEEKLY REPORT

### Is it Implemented?
- **YES** - `/api/workflow/weekly-report` endpoint
- **Service:** orchestrator.run_weekly_report()

### How Generated?
- **Pipeline:** 6-stage orchestration
  1. Resume Intelligence (fetch from DB)
  2. Market Intelligence (aggregate companies)
  3. Company Intelligence (skill matching)
  4. Career Intelligence (skill gap analysis)
  5. Opportunity Ranking (top 3 matches)
  6. Report Assembly (cover letter + summary)

### Real AI?
- **Partial:**
  - Resume extraction: YES (OpenRouter)
  - Company discovery: YES (Tavily + Firecrawl + OpenAI)
  - Matching: NO (deterministic)
  - Career intelligence: NO (deterministic)
  - Cover letter: YES (OpenRouter)

### Mock?
- **NO** - Uses real resume + real/seed companies
- Delays are simulated (time.sleep) but data is real

### JSON?
- **YES** - Returns structured JSON payload

### Markdown?
- **NO** - No markdown output

### Prompt?
- **YES** - Inline prompts in service files
- No external prompt files

### PDF?
- **NO** - No PDF generation

---

## STEP 10: COVER LETTER

### Prompt
- **Location:** llm_service.py line 96-144
- **Style:** Deterministic template with variable substitution
- **Requirements:**
  - 250-350 words
  - Reference 2+ specific skills
  - Reference company tagline/industry
  - No fabricated achievements
  - No markdown
  - Plain text only
  - Open with "Dear Hiring Team,"
  - Close with "Sincerely," + name

### Model
- **Provider:** OpenRouter
- **Model:** anthropic/claude-3.5-sonnet (configurable)
- **Fallback:** None (returns None on failure)

### Streaming?
- **NO** - Blocking call

### Fallback?
- **YES** - Returns None on any failure
- Orchestrator continues without cover letter

### Mock?
- **NO** - Real AI generation

---

## STEP 11: ERROR HANDLING

### Exception Handling
- **Level:** Good
- **Resume upload:** HTTPException for validation errors, general exception for unexpected errors
- **AI services:** Logged, graceful degradation (fallback or None)
- **Discovery:** Raises exception, caller falls back to seed
- **Cover letter:** Returns None on failure

### Validation
- **Resume upload:**
  - File type validation (PDF only)
  - File size validation (10MB max)
  - Empty file check
- **API inputs:** Pydantic schemas

### Timeouts
- **LLMService:** 10.0 second timeout (httpx)
- **Discovery:** 10.0 second timeout (Tavily, Firecrawl)
- **Configurable:** NO (hardcoded)

### Retry Logic
- **Resume extraction:** 1 retry on JSON parse failure
- **Discovery:** NO retry
- **Cover letter:** NO retry

### Logging
- **Level:** Comprehensive
- **Library:** Python logging
- **Configuration:** app/core/logging.py
- **Coverage:** All services log errors and warnings

### API Failures
- **Graceful degradation:** YES
- **Fallback to seed data:** YES (discovery)
- **Fallback to local parser:** YES (resume)
- **Continue without feature:** YES (cover letter)

---

## STEP 12: SECURITY

### Secrets
- **Storage:** Environment variables (.env)
- **Keys:** OPENROUTER_API_KEY, TAVILY_API_KEY, FIRECRAWL_API_KEY, OPENAI_API_KEY
- **Status:** Configured but optional (graceful degradation)

### API Keys
- **Required:** NO (all optional, graceful fallback)
- **Validation:** Checks if configured before use
- **Exposure:** Not logged in error messages

### CORS
- **Implemented:** YES
- **Configuration:** ALLOWED_ORIGINS in config.py
- **Origins:** localhost:3000, localhost:5173, 127.0.0.1:3000, 127.0.0.1:5173
- **Methods:** All allowed
- **Headers:** All allowed
- **Credentials:** YES

### Validation
- **Input:** Pydantic schemas
- **File:** Type, size, emptiness checks
- **Output:** None (no response validation)

### Rate Limiting
- **Implemented:** NO
- **Status:** MISSING

### Authentication
- **Implemented:** NO
- **Status:** MISSING
- **Access:** Open to all

### Authorization
- **Implemented:** NO
- **Status:** MISSING

### File Validation
- **Type:** PDF only (MIME type + extension)
- **Size:** 10MB max
- **Content:** Emptiness check
- **Malware scan:** NO

### Prompt Injection Protection
- **Implemented:** NO
- **Status:** MISSING
- **Risk:** LOW (user input only in resume, not in system prompts)

---

## STEP 13: PERFORMANCE

### Caching
- **Implemented:** YES (file-based)
- **Location:** cache/latest_discovery.json
- **TTL:** 24 hours
- **Scope:** Company discovery only
- **Pre-warming:** YES (background thread on startup)
- **Invalidation:** Time-based (no manual invalidation)

### Async
- **Implemented:** NO
- **Status:** All endpoints are synchronous
- **Blocking:** YES

### Blocking Calls
- **External APIs:** YES (Tavily, Firecrawl, OpenRouter, OpenAI)
- **Timeouts:** 10 seconds per call
- **Impact:** Can be slow on cache miss

### Repeated API Calls
- **Discovery:** NO (cached)
- **Resume extraction:** NO (extracted once per upload)
- **Cover letter:** YES (generated per request, no caching)

### Database Optimization
- **Indexes:** Primary key only
- **Queries:** Simple (latest resume, by ID)
- **Optimization:** Minimal (single table, small dataset)

### Memory Usage
- **Status:** Good
- **In-memory:** Company dataset (20-40 companies, small)
- **Risk:** LOW

---

## STEP 14: TECHNICAL DEBT

### TODOs
- 1 comment in orchestrator.py about replacing simulated delays with real AI work

### Placeholders
- Simulated delays in orchestrator.py (time.sleep) - These are intentional placeholders, not technical debt

### Stubs
- `/api/companies/discover` - Returns 501 "Not Implemented Yet - Coming in Milestone 3"
- `/api/companies/match` - Returns 501 "Not Implemented Yet - Coming in Milestone 5"

### Temporary Implementations
- **Simulated workflow delays:** Intentional for UX, not temporary
- **File-based cache:** Working solution, may want Redis in production
- **SQLite:** Production may want PostgreSQL

### Unused Files
- **None detected**

### Unused Endpoints
- `/api/companies/discover` - Stub
- `/api/companies/match` - Stub

### Missing Features
- Authentication
- Authorization
- Rate limiting
- Pagination
- Company filtering API
- Company sorting API
- Embeddings-based matching
- Experience-weighted matching
- PDF report generation
- Email delivery
- User accounts
- Session management

---

## STEP 15: FINAL SCORECARD

| Feature | Status | Confidence |
|----------|--------|-------------|
| Resume Upload | IMPLEMENTED | HIGH |
| Resume Parsing | IMPLEMENTED | HIGH |
| Resume Extraction | IMPLEMENTED | HIGH |
| Company Dataset | IMPLEMENTED (seed + discovery) | HIGH |
| Search | PARTIAL (API stub, works via frontend) | MEDIUM |
| Filtering | PARTIAL (API stub, works via frontend) | MEDIUM |
| Matching | IMPLEMENTED (deterministic) | HIGH |
| Skill Gap | IMPLEMENTED (deterministic) | HIGH |
| Career Report | IMPLEMENTED | HIGH |
| Cover Letter | IMPLEMENTED | HIGH |
| Dashboard APIs | IMPLEMENTED | HIGH |
| Workflow | IMPLEMENTED (with simulated delays) | MEDIUM |
| Caching | IMPLEMENTED (file-based) | MEDIUM |
| Security | NOT IMPLEMENTED | N/A |
| Authentication | NOT IMPLEMENTED | N/A |

---

## STEP 16: PRIORITY ROADMAP

### Priority 1 (Critical for Production)
1. **Add Authentication & Authorization** - Currently open to all users, no session management
2. **Add Rate Limiting** - Prevent API abuse, especially expensive AI calls
3. **Add Pagination** - Companies endpoint returns full dataset, not scalable
4. **Add API-Level Filtering & Sorting** - Offload frontend work to backend
5. **Add Redis Cache** - Replace file-based cache for production scalability
6. **Add Request Validation Middleware** - Centralized input validation
7. **Add Error Monitoring** - Sentry or similar for production debugging
8. **Add File Scanning** - Malware/virus scan for uploaded resumes

### Priority 2 (Important for UX)
9. **Replace Simulated Delays with Real Async Work** - Current time.sleep is fake
10. **Add Cover Letter Caching** - Re-generating on every request is wasteful
11. **Add User Accounts** - Persist user data across sessions
12. **Add Resume History** - Allow users to view/upload multiple resumes
13. **Add Company Favorites** - Allow users to save interesting companies
14. **Add Report History** - Save previous weekly reports
15. **Improve Matching Algorithm** - Factor in experience, education, role relevance
16. **Add Embeddings-Based Matching** - Semantic matching vs keyword matching

### Priority 3 (Nice to Have)
17. **Implement `/api/companies/discover`** - Currently stubbed
18. **Implement `/api/companies/match`** - Currently stubbed
19. **Add PDF Report Generation** - Generate downloadable PDF reports
20. **Add Email Delivery** - Email reports to users
21. **Add Webhook Support** - Notify external systems
22. **Add Admin Dashboard** - Internal tooling
23. **Add Analytics** - Track usage, popular companies, matching success
24. **Add A/B Testing** - Test different matching algorithms
25. **Add Multi-language Support** - Support non-English resumes

---

## CONCLUSION

**Overall Assessment:** The backend is **FUNCTIONAL** and **WELL-ARCHITECTED** for an MVP. The core workflow (resume upload → AI extraction → company matching → report generation) works end-to-end with real AI integrations (OpenRouter, Tavily, Firecrawl, OpenAI).

**Strengths:**
- Clean architecture with proper separation of concerns
- Real AI integrations (not mock data)
- Graceful degradation (fallbacks everywhere)
- Good error handling and logging
- Deterministic matching (auditable)
- File-based caching (pre-warmed on startup)

**Weaknesses:**
- No authentication/authorization
- No rate limiting
- No pagination
- Simulated workflow delays (fake UX)
- File-based cache (not production-ready)
- Keyword-only matching (no semantic understanding)
- No user accounts or session management
- Stubs for discover/match endpoints

**Production Readiness:** **LOW** - Requires security, scalability, and performance improvements before production deployment.

**MVP Readiness:** **HIGH** - Functional for demo/prototype use with API keys configured.
