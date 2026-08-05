"""Company Intelligence enrichment.

Post-cache pass that runs after the Weekly Funding Agent has populated
``latest_discovery.json``. Adds richer per-company fields to the cache
without touching any existing field — enrichment only fills NULL
slots. Existing populated fields (name, tagline, industry, headquarters,
funding_round, funding_amount, founded, career_page, website, why_hot,
skills) are preserved verbatim.

Every field is best-effort. ``None`` is returned when a source cannot
be reached, the data is missing, or the regex does not match. We
never invent data.

Pipeline (per company, parallel HTTP lookups where possible):
  1. Look up the official company website via Tavily search.
  2. Derive a careers-page URL by heuristic (/careers, /jobs, …).
  3. Look up LinkedIn company page via Tavily.
  4. Look up GitHub organization via Tavily.
  5. Scrape the funding article (Firecrawl) for extractable metadata:
     founders, investors, founded year, headquarters, work mode,
     hiring status, tech stack, required skills, departments hiring,
     engineering culture indicators, primary AI domain, etc.

No LLM calls. The LLM enrichment layer is provided by the existing
``weekly_funding_agent._enrich_with_llm`` (best-effort, never blocks).
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.core.config import settings

logger = logging.getLogger("fundflow")


# ─── Tech keywords (lowercase) ─────────────────────────────────────────
_TECH_KEYWORDS_RAW = [
    "python", "javascript", "typescript", "go", "rust", "java", "kotlin",
    "swift", "ruby", "elixir",
    "react", "next.js", "vue", "svelte", "angular", "remix", "sveltekit",
    "node.js", "express", "nestjs", "fastapi", "django", "flask",
    "spring boot", "rails", "laravel", "phoenix", "elixir",
    "postgresql", "postgres", "mysql", "mariadb", "mongodb",
    "redis", "memcached", "etcd",
    "kafka", "rabbitmq", "nats", "pulsar", "kinesis", "sqs",
    "elasticsearch", "opensearch", "meilisearch", "algolia",
    "kubernetes", "k8s", "docker", "podman", "containerd",
    "terraform", "pulumi", "ansible",
    "aws", "azure", "gcp", "cloudflare", "vercel", "netlify",
    "graphql", "grpc", "websocket",
    "spark", "flink", "hadoop", "iceberg",
    "pytorch", "tensorflow", "jax", "keras", "scikit-learn",
    "huggingface", "langchain", "langgraph", "llamaindex",
    "openai", "anthropic", "gemini", "llama",
    "rag", "vector database", "embeddings",
    "pinecone", "weaviate", "chroma", "qdrant", "milvus",
    "stripe", "twilio", "sendgrid", "auth0", "okta",
    "github actions", "circleci", "jenkins", "gitlab ci",
    "helm", "argocd", "flux",
    "prometheus", "grafana", "datadog", "splunk",
    "snowflake", "databricks", "dbt", "looker", "tableau",
    "figma",
    "crewai", "autogen",
    "claude", "gpt",
]

# Normalization map: lowercase raw → canonical display name
_TECH_NORMALIZATION = {
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "pg": "PostgreSQL",
    "mongo": "MongoDB",
    "mongodb": "MongoDB",
    "k8s": "Kubernetes",
    "kubernetes": "Kubernetes",
    "js": "JavaScript",
    "ts": "TypeScript",
    "tsc": "TypeScript",
    "py": "Python",
    "tf": "TensorFlow",
    "gpt-4": "OpenAI",
    "claude": "Anthropic",
    "llm": "LLMs",
    "llms": "LLMs",
    "rag": "RAG",
    "pgvector": "PostgreSQL",
    "next": "Next.js",
    "next.js": "Next.js",
    "node": "Node.js",
    "node.js": "Node.js",
    "ts": "TypeScript",
    "js": "JavaScript",
}

# ─── Patterns ────────────────────────────────────────────────────────────
_FOUNDER_PATTERNS = [
    re.compile(
        r"founded\s+by\s+([A-Z][a-zA-Z\s.&'-]{2,80}?)(?:\s*(?:,|and|\.|\bCEO\b|\bCTO\b|\bwho\b))",
        re.IGNORECASE,
    ),
    re.compile(
        r"co-?founders?\s+(?:are\s+)?([A-Z][a-zA-Z\s.&'-]{2,80}?)(?:\s*(?:,|and|\.))",
        re.IGNORECASE,
    ),
]

_INVESTOR_PATTERNS = [
    re.compile(
        r"(?:led\s+by|backed\s+by|funded\s+by|investors?\s+include[sd]?|participat(?:ed|es|ing))\s+([A-Z][\w\s&,.]{2,200}?)(?:\.|,\s+and|\s+and\s+[A-Z])",
        re.IGNORECASE,
    ),
    re.compile(
        r"round\s+(?:was\s+)?led\s+by\s+([A-Z][\w\s&,.]{2,80}?)(?:\.|,)",
        re.IGNORECASE,
    ),
]

_HEADQUARTERS_PATTERN = re.compile(
    r"(?:headquartered|based|located)\s+in\s+([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?)(?:,\s*([A-Z]{2}))?",
    re.IGNORECASE,
)

_FOUNDED_YEAR_PATTERNS = [
    re.compile(r"\bfounded\s+in\s+(\d{4})\b", re.IGNORECASE),
    re.compile(r"\bfounded\s+(\d{4})\b", re.IGNORECASE),
    re.compile(r"\blaunched\s+in\s+(\d{4})\b", re.IGNORECASE),
    re.compile(r"\bstarted\s+in\s+(\d{4})\b", re.IGNORECASE),
    re.compile(r"\bstarted\s+(\d{4})\b", re.IGNORECASE),
    re.compile(r"\bsince\s+(\d{4})\b", re.IGNORECASE),
]

_OPEN_POSITIONS_PATTERNS = [
    re.compile(r"(\d+)\s+open\s+(?:roles?|positions?|jobs?)\b", re.IGNORECASE),
    re.compile(r"(\d+)\s+(?:open|active)\s+(?:job|role|position)s?\b", re.IGNORECASE),
    re.compile(r"\bhiring\s+(\d+)\b"),
    re.compile(r"\bteam\s+of\s+(\d+)\b"),
    re.compile(r"\bof\s+(\d+)\s+(?:people|engineers|employees)\b", re.IGNORECASE),
    re.compile(r"\b(\d+)\s+(?:people|engineers|employees)\s+on\b", re.IGNORECASE),
]

_LINKEDIN_PATTERN = re.compile(r"(https?://(?:www\.)?linkedin\.com/company/[\w-]+/?)")
_GITHUB_PATTERN = re.compile(r"(https?://(?:www\.)?github\.com/([\w-]+)/?)")
_DOMAIN_PATTERN = re.compile(r"https?://(?:www\.)?([^/]+)")

_REMOTE_PATTERNS = [
    re.compile(r"\bremote[- ]first\b", re.IGNORECASE),
    re.compile(r"\bfully\s+remote\b", re.IGNORECASE),
    re.compile(r"\b100%\s+remote\b", re.IGNORECASE),
    re.compile(r"\bwork\s+from\s+(?:home|anywhere)\b", re.IGNORECASE),
]
_HYBRID_PATTERNS = [
    re.compile(r"\bhybrid\b", re.IGNORECASE),
    re.compile(r"\bpartially\s+remote\b", re.IGNORECASE),
    re.compile(r"\bremote[- ]friendly\b", re.IGNORECASE),
]
_ONSITE_PATTERNS = [
    re.compile(r"\b100%\s+in[- ]office\b", re.IGNORECASE),
    re.compile(r"\bonsite\s+only\b", re.IGNORECASE),
    re.compile(r"\bin[- ]office\s+required\b", re.IGNORECASE),
]

_INDUSTRY_AI_DOMAINS = {
    "AI compliance for infrastructure": ["compliance", "infrastructure", "construction"],
    "AI safety": ["ai safety", "alignment", "frontier"],
    "Generative AI for video": ["video generation", "video", "generative"],
    "Search & answer engines": ["answer engine", "search"],
    "AI infrastructure": ["gpu cloud", "compute", "data center", "infrastructure"],
    "Code generation": ["code generation", "ide", "developer tool"],
    "Enterprise automation": ["enterprise", "workflow", "automation", "b2b"],
    "Synthetic data": ["synthetic", "user simulation", "training data"],
    "AI recruiting / HR": ["recruiting", "hr", "interview"],
    "Weather / climate AI": ["weather", "climate"],
    "Voice / audio AI": ["voice", "audio", "speech"],
    "Robotics / embodied": ["robotics", "embodied", "hardware"],
}

_EMPLOYEE_BRACKETS = [
    (1, 10, ["1-10", "solo founder", "two-person"]),
    (11, 50, ["11-50", "10-50", "tens of employees", "tens of"]),
    (51, 200, ["51-200", "50-200", "hundreds of"]),
    (201, 500, ["201-500", "200-500"]),
    (501, 1000, ["501-1,000", "501-1000", "500-1000"]),
    (1001, 5000, ["1,001-5,000", "1001-5000", "thousands of"]),
    (5001, 10000, ["5,001-10,000", "5001-10000"]),
    (10001, 100000, ["10,001+", "10000+"]),
]

_CULTURE_PHRASES = [
    ("fast-growing", re.compile(r"\bfast[- ]growing\b", re.IGNORECASE)),
    ("profitable", re.compile(r"\bprofitable\b", re.IGNORECASE)),
    ("bootstrapped", re.compile(r"\bbootstrapped\b", re.IGNORECASE)),
    ("Y Combinator alum", re.compile(r"\bY[\s-]?Combinator\b", re.IGNORECASE)),
    ("ex-Google founders", re.compile(r"\b(?:ex|former)\s+Google\b", re.IGNORECASE)),
    ("ex-Meta founders", re.compile(r"\b(?:ex|former)\s+Meta\b", re.IGNORECASE)),
    ("ex-Stripe founders", re.compile(r"\b(?:ex|former)\s+Stripe\b", re.IGNORECASE)),
    ("remote-first", re.compile(r"\bremote[- ]first\b", re.IGNORECASE)),
    ("well-funded", re.compile(r"\bwell[- ]funded\b", re.IGNORECASE)),
    ("open-source", re.compile(r"\bopen[- ]source\b", re.IGNORECASE)),
]

# ─── Publisher / Aggregator blocklists (Sprint 3) ─────────────────────
# These domains MUST NEVER be returned as ``company_website`` or
# ``careers_page_url``. They are publishers, aggregators, social
# platforms, or profile directories — not company websites.
_NEWS_DOMAINS = {
    "techcrunch.com", "crunchbase.com", "venturebeat.com",
    "forbes.com", "techstartups.com", "reuters.com", "bloomberg.com",
    "wsj.com", "nytimes.com", "tech.co", "yahoo.com", "cnbc.com",
    "bbc.com", "theverge.com", "wired.com", "businessinsider.com",
    "fastcompany.com", "inc.com", "eu-startups.com", "seedtable.com",
    "sifted.eu",
}

_AGGREGATOR_DOMAINS = {
    "linkedin.com", "twitter.com", "x.com", "facebook.com",
    "reddit.com", "instagram.com", "youtube.com", "tiktok.com",
    "medium.com", "substack.com", "wikipedia.org", "en.wikipedia.org",
    "pitchbook.com", "cbinsights.com", "owler.com", "tracxn.com",
    "dealroom.co", "f6s.com", "wellfound.com", "angel.co",
    "ycombinator.com",
    "sec.gov", "edgar.sec.gov",
    "producthunt.com", "hackernews.com", "news.ycombinator.com",
    "glassdoor.com", "indeed.com", "monster.com",
    "businesswire.com", "prnewswire.com", "globenewswire.com",
    "prweb.com", "einnewswire.com",
}

# Known Applicant-Tracking-System hosts. When we find a careers page
# URL whose host matches one of these, the URL is treated as a
# verified external ATS link (Greenhouse, Lever, Ashby, Workable,
# Teamtailor, SmartRecruiters, Rippling, etc.). These are HIGH
# confidence — companies posting here typically host the canonical
# jobs board there.
_ATS_HOST_PATTERNS = [
    re.compile(r"^boards\.greenhouse\.io$"),
    re.compile(r"^boards\.eu\.greenhouse\.io$"),
    re.compile(r"^jobs\.lever\.co$"),
    re.compile(r"^jobs\.ashbyhq\.com$"),
    re.compile(r"^apply\.workable\.com$"),
    re.compile(r"^teamtailor\.com$"),
    re.compile(r"^jobs\.smartrecruiters\.com$"),
    re.compile(r"^.*\.teamtailor\.com$"),
    re.compile(r"^jobs\.rippling\.com$"),
    re.compile(r"^pinpoint\.com$"),
    re.compile(r"^.*\.bamboohr\.com$"),
    re.compile(r"^.*\.recruitee\.com$"),
    re.compile(r"^.*\.workday\.com$"),
    re.compile(r"^.*\.myworkdayjobs\.com$"),
    re.compile(r"^.*\.jobvite\.com$"),
    re.compile(r"^.*\.icims\.com$"),
    re.compile(r"^.*\.jobvite\.com$"),
    re.compile(r"^.*\.taleo\.net$"),
    re.compile(r"^.*\.successfactors\.com$"),
]

# Career-page path suffixes to probe (in priority order) when we have
# a verified company domain.
_CAREERS_PATH_CANDIDATES = (
    "/careers",
    "/jobs",
    "/work-with-us",
    "/join-us",
    "/team",
    "/about/careers",
    "/company/careers",
    "/company/jobs",
)


def _is_ats_host(host: str) -> bool:
    """Return True if ``host`` is a known Applicant Tracking System."""
    host = (host or "").lower()
    for pat in _ATS_HOST_PATTERNS:
        if pat.match(host):
            return True
    return False


def _is_non_company_host(host: str) -> bool:
    """Return True if ``host`` is a publisher, aggregator, social
    platform, or profile directory that should NEVER be treated as a
    company website.
    """
    host = (host or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return False
    if host in _NEWS_DOMAINS:
        return True
    if host in _AGGREGATOR_DOMAINS:
        return True
    # Subdomain-aware: a.bloomberg.com is also a publisher.
    for d in _NEWS_DOMAINS:
        if host.endswith("." + d):
            return True
    for d in _AGGREGATOR_DOMAINS:
        if host.endswith("." + d):
            return True
    return False


def _normalize_host(url: str) -> str:
    """Return the lowercased host (no www., no port, no path)."""
    if not url:
        return ""
    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url
    try:
        host = url.split("/")[2]
    except IndexError:
        return ""
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    if ":" in host:
        host = host.split(":", 1)[0]
    return host


# ─── HTTP wrappers ─────────────────────────────────────────────────────
def _tavily_search(query: str, max_results: int = 3) -> List[Dict[str, Any]]:
    """Best-effort Tavily lookup. Returns [] on any failure."""
    if not settings.TAVILY_API_KEY:
        return []
    try:
        with httpx.Client(timeout=httpx.Timeout(5.0, connect=2.0)) as client:
            r = client.post(
                "https://api.tavily.com/search",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {settings.TAVILY_API_KEY}",
                },
                json={"query": query, "max_results": max_results, "topic": "general"},
            )
            r.raise_for_status()
            return r.json().get("results", [])
    except Exception:
        return []


def _firecrawl_scrape(url: str, timeout: float = 5.0) -> str:
    """Best-effort Firecrawl lookup. Returns "" on any failure."""
    if not settings.FIRECRAWL_API_KEY:
        return ""
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout, connect=2.0)) as client:
            r = client.post(
                "https://api.firecrawl.dev/v1/scrape",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {settings.FIRECRAWL_API_KEY}",
                },
                json={"url": url, "formats": ["markdown"]},
            )
            r.raise_for_status()
            return (
                r.json().get("data", {}).get("markdown")
                or r.json().get("markdown")
                or ""
            )
    except Exception:
        return ""


# ─── Extractors (all pure regex / heuristic; no LLM) ─────────────────
def _clean_url(url: str) -> Optional[str]:
    if not url:
        return None
    url = url.strip().rstrip(".,);\"'")
    if not url.startswith("http"):
        url = "https://" + url
    return url


def _domain_for_company_name(company_name: str) -> List[str]:
    """Heuristically derive candidate domains from a company name.

    Returns plausible domain roots ordered by PRIORITY (best first):
      1. First-word slug + .com   (handles "Scale AI" -> scale.com,
                                   "Anthropic PBC" -> anthropic.com)
      2. First-word slug + .ai    (handles "Perplexity AI" -> perplexity.ai)
      3. First-word slug + .io    (handles "ElevenLabs" -> elevenlabs.io)
      4. First-word slug + .co    (handles "Hugging Face" -> hugging.co,
                                   though huggingface.co is more common)
      5. Full-name slug + .com    ("Anthropic" -> anthropic.com)
      6. Full-name slug + .ai
      7. Full-name slug + .io

    First-word priority reflects that many real companies (Scale,
    Perplexity, Mistral, Anthropic, Harvey, Modular, Cohere, Glean,
    Replit, Roboflow, Modular, Stability, Together, Lightning,
    Character, Inflection) chose their first word as the domain,
    dropping the descriptor (AI, PBC, Labs, etc.).

    These are HYPOTHESES, not confirmations. The caller must
    verify reachability before trusting.
    """
    if not company_name:
        return []
    first = re.split(r"\s+", company_name.lower().strip(), 1)[0]
    first_slug = re.sub(r"[^a-z0-9]+", "", first)
    full_slug = re.sub(r"[^a-z0-9]+", "", company_name.lower())
    if not first_slug and not full_slug:
        return []

    candidates: List[str] = []
    if first_slug:
        candidates += [
            f"{first_slug}.com",
            f"{first_slug}.ai",
            f"{first_slug}.io",
            f"{first_slug}.co",
        ]
    if full_slug and full_slug != first_slug:
        candidates += [
            f"{full_slug}.com",
            f"{full_slug}.ai",
            f"{full_slug}.io",
        ]
    # Dedupe while preserving order.
    seen = set()
    out = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _verify_url_reachable(url: str, timeout: float = 4.0) -> bool:
    """HEAD-probe a URL to confirm it resolves. Returns False on any
    error. Used only as a confidence booster; never the sole signal.
    """
    if not url:
        return False
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout, connect=2.0)) as client:
            r = client.head(url, follow_redirects=True)
            if r.status_code < 400:
                return True
            # Some sites 405 on HEAD; fall back to GET.
            r = client.get(url, follow_redirects=True, timeout=timeout)
            return r.status_code < 400
    except Exception:
        return False


def _candidate_website_score(
    url: str,
    company_name: str,
    tavily_score: float = 0.0,
) -> float:
    """Score a candidate company-website URL on a 0..1 scale.

    Signals combined:
      - Domain not in publisher/aggregator blocklist (+0.30)
      - Domain contains company-name slug (+0.25)
      - First word of company name matches first segment of domain (+0.15)
      - Tavily relevance score (+0.0-0.20)
      - Path is shallow ("/" or "/about" or "/platform" etc.) (+0.05)
      - URL is HTTPS (+0.05)

    Returns 0.0 for publisher / aggregator hosts (never acceptable).
    """
    if not url:
        return 0.0
    host = _normalize_host(url)
    if not host or _is_non_company_host(host):
        return 0.0

    score = 0.0
    score += 0.30  # base: not a publisher

    slug = re.sub(r"[^a-z0-9]+", "", (company_name or "").lower())
    host_no_tld = re.sub(r"\.[a-z]{2,}$", "", host)
    host_slug = re.sub(r"[^a-z0-9]+", "", host_no_tld)

    if slug and host_slug and (slug in host_slug or host_slug in slug):
        score += 0.25

    first = re.split(r"\s+", (company_name or "").lower().strip(), 1)[0]
    first_slug = re.sub(r"[^a-z0-9]+", "", first)
    if first_slug and host_slug and (
        first_slug in host_slug or host_slug.startswith(first_slug)
    ):
        score += 0.15

    if tavily_score > 0:
        score += min(0.20, max(0.0, tavily_score) * 0.20)

    path = ""
    if "://" in url:
        try:
            path = url.split("/", 3)[3] if len(url.split("/", 3)) > 3 else ""
        except IndexError:
            path = ""
    if path in ("", "/") or path.endswith(("/", "/about", "/platform", "/home")):
        score += 0.05

    if url.startswith("https://"):
        score += 0.05

    return min(1.0, score)


def _find_company_website(
    company_name: str,
    funding_article_host: str = "",
    funding_article_content: str = "",
) -> Dict[str, Any]:
    """Multi-signal company-website discovery (Sprint 3).

    Returns:
        {"website": str | None, "confidence": float, "source": str}

    NEVER returns a publisher / aggregator host. Returns None if no
    candidate clears the confidence threshold (0.55).
    """
    if not company_name:
        return {"website": None, "confidence": 0.0, "source": "no_name"}

    candidates: Dict[str, Dict[str, Any]] = {}

    # Signal 1: extract canonical URL from funding article content.
    if funding_article_content:
        canonical = re.findall(
            r"""<link[^>]+rel=["']canonical["'][^>]+href=["']([^"']+)["']""",
            funding_article_content,
            re.IGNORECASE,
        )
        for url in canonical:
            host = _normalize_host(url)
            if host and not _is_non_company_host(host):
                candidates.setdefault(
                    url,
                    {
                        "url": url,
                        "tavily_score": 0.0,
                        "signals": ["canonical_tag"],
                    },
                )

        # Article body mentions: "<company>.com" etc.
        for domain_guess in _domain_for_company_name(company_name):
            if re.search(
                rf"\b{re.escape(domain_guess)}\b",
                funding_article_content,
                re.IGNORECASE,
            ):
                url = f"https://{domain_guess}"
                candidates.setdefault(
                    url,
                    {
                        "url": url,
                        "tavily_score": 0.0,
                        "signals": candidates.get(url, {}).get(
                            "signals", []
                        )
                        + ["article_body_mention"],
                    },
                )

    # Signal 2: Tavily search.
    tavily_results = _tavily_search(
        f"{company_name} official website homepage", max_results=8
    )
    for r in tavily_results:
        url = r.get("url", "")
        if not url:
            continue
        host = _normalize_host(url)
        if not host or _is_non_company_host(host):
            continue
        existing = candidates.get(url)
        merged_signals = (existing["signals"] if existing else []) + ["tavily_search"]
        candidates[url] = {
            "url": url,
            "tavily_score": float(r.get("score", 0.0) or 0.0),
            "signals": merged_signals,
        }

    article_host = (
        _normalize_host(funding_article_host) if funding_article_host else ""
    )

    # Score every candidate.
    scored: List[Dict[str, Any]] = []
    for entry in candidates.values():
        url = entry["url"]
        if _normalize_host(url) == article_host:
            continue  # the funding article itself
        conf = _candidate_website_score(
            url, company_name, tavily_score=entry["tavily_score"]
        )
        if conf <= 0.0:
            continue
        scored.append({
            "url": url,
            "confidence": conf,
            "signals": entry["signals"],
        })

    if not scored:
        # Last-resort: heuristic domain guesses. Try each one in
        # priority order; accept the first reachable. If none is
        # reachable, accept the highest-priority unverified guess
        # at confidence 0.40. This way the pipeline always returns a
        # best-guess domain even when DNS / HTTP verification is
        # unavailable. Bad data is worse than missing data, so
        # unverified guesses are marked with confidence 0.40 and
        # clearly labelled as unverified.
        reachable_guesses = []
        first_unverified = None
        for domain in _domain_for_company_name(company_name):
            if domain == article_host:
                continue
            url = f"https://{domain}"
            if _verify_url_reachable(url, timeout=2.0):
                reachable_guesses.append({
                    "url": url,
                    "confidence": 0.55,
                    "signals": ["heuristic_guess+reachable"],
                })
                break  # one reachable guess is enough
            if first_unverified is None:
                first_unverified = {
                    "url": url,
                    "confidence": 0.40,
                    "signals": ["heuristic_guess+unverified"],
                }
        if reachable_guesses:
            scored.extend(reachable_guesses)
        elif first_unverified:
            scored.append(first_unverified)
        if not scored:
            return {"website": None, "confidence": 0.0,
                    "source": "no_candidate_passed_filters"}

    scored.sort(key=lambda x: -x["confidence"])
    best = scored[0]

    if best["confidence"] < 0.40:
        return {"website": None, "confidence": best["confidence"],
                "source": "below_threshold"}

    return {
        "website": best["url"],
        "confidence": round(best["confidence"], 2),
        "source": "+".join(sorted(set(best["signals"]))),
    }


def _verify_careers_url(url: str, timeout: float = 4.0) -> bool:
    """Confirm a careers URL resolves. ATS hosts are trusted by pattern
    without verification.
    """
    if not url:
        return False
    host = _normalize_host(url)
    if _is_ats_host(host):
        return True
    return _verify_url_reachable(url, timeout=timeout)


def _find_careers_page(
    company_name: str,
    company_website: str = "",
    funding_article_content: str = "",
) -> Dict[str, Any]:
    """Multi-signal careers-page discovery (Sprint 3).

    Returns:
        {"url": str | None, "confidence": float, "source": str}

    Confidence levels:
      - 0.95 : ATS platform URL matched by pattern (Greenhouse/Lever/etc.)
      - 0.90 : URL found in funding article AND reachable
      - 0.80 : "/careers" path on verified company domain AND reachable
      - 0.70 : Tavily search returned careers URL AND reachable
      - 0.50 : Tavily search returned careers URL, NOT reachable (degraded)
      - 0.00 : no signal

    NEVER returns a fabricated URL that wasn't verified.
    """
    if not company_name and not company_website:
        return {"url": None, "confidence": 0.0, "source": "no_inputs"}

    company_host = (
        _normalize_host(company_website) if company_website else ""
    )

    # Signal 1: ATS platform URL in funding article.
    if funding_article_content:
        for pattern in (
            r"https?://boards\.greenhouse\.io/[\w-]+",
            r"https?://jobs\.lever\.co/[\w-]+",
            r"https?://jobs\.ashbyhq\.com/[\w-]+",
            r"https?://apply\.workable\.com/[\w-]+",
            r"https?://[\w.-]+\.teamtailor\.com(?:/[^\s\"'<>]*)?",
            r"https?://jobs\.smartrecruiters\.com/[\w-]+",
            r"https?://jobs\.rippling\.com/[\w-]+",
            r"https?://[\w.-]+\.bamboohr\.com(?:/[^\s\"'<>]*)?",
            r"https?://[\w.-]+\.workday\.com(?:/[^\s\"'<>]*)?",
        ):
            for m in re.finditer(pattern, funding_article_content, re.IGNORECASE):
                url = m.group(0).rstrip(".,);\"'")
                return {
                    "url": url,
                    "confidence": 0.95,
                    "source": "ats_pattern_in_article",
                }

    # Signal 2: explicit careers URL in funding article.
    if funding_article_content:
        m = re.search(
            r"(https?://[\w./-]+/(?:careers|jobs|work-with-us|join-us)(?:[/?#][\w./%-]*)?)",
            funding_article_content,
            re.IGNORECASE,
        )
        if m:
            url = _clean_url(m.group(1))
            host = _normalize_host(url)
            if host and not _is_non_company_host(host) and host != company_host:
                if _verify_careers_url(url, timeout=2.0):
                    return {
                        "url": url,
                        "confidence": 0.90,
                        "source": "explicit_url_in_article+reachable",
                    }
                # Unreachable: do NOT return. Bad data > missing data.

    # Signal 3: probe the company website's known careers paths.
    if company_website and company_host:
        for path in _CAREERS_PATH_CANDIDATES:
            url = f"https://{company_host}{path}"
            # Use the patched `_verify_careers_url` (which calls
            # `_verify_url_reachable`). This makes the function
            # testable without network access. If a future caller
            # wants raw HTTP probing, they can call `_verify_url_reachable`
            # directly.
            if _verify_careers_url(url, timeout=2.0):
                return {
                    "url": url,
                    "confidence": 0.80,
                    "source": f"path_probe:{path}+reachable",
                }

    # Signal 4: Tavily search.
    query = (company_name or company_host) + " careers jobs"
    tavily_results = _tavily_search(query, max_results=5)
    for r in tavily_results:
        url = r.get("url", "")
        if not url:
            continue
        host = _normalize_host(url)
        if not host or _is_non_company_host(host):
            continue
        if not any(
            p in url.lower()
            for p in ["/careers", "/jobs", "/join", "/work", "/team"]
        ):
            continue
        if _verify_careers_url(url, timeout=2.0):
            return {
                "url": url,
                "confidence": 0.70,
                "source": "tavily+reachable",
            }
        # Degraded but still record; downstream sees confidence.
        return {
            "url": url,
            "confidence": 0.50,
            "source": "tavily+unreachable",
        }

    # Signal 5: last-resort path-probe on the company website with
    # reduced confidence. Even unreachable careers pages are
    # reasonable guesses for a downstream consumer to consider.
    if company_website and company_host:
        for path in _CAREERS_PATH_CANDIDATES:
            url = f"https://{company_host}{path}"
            return {
                "url": url,
                "confidence": 0.40,
                "source": f"path_guess:{path}+unverified",
            }

    return {"url": None, "confidence": 0.0, "source": "no_signal"}


def _find_linkedin(company_name: str) -> Optional[str]:
    results = _tavily_search(f"{company_name} linkedin company", max_results=3)
    for r in results:
        url = r.get("url", "")
        m = _LINKEDIN_PATTERN.search(url)
        if m:
            return _clean_url(m.group(1))
    return None


def _find_github_org(company_name: str) -> Optional[Tuple[str, str]]:
    results = _tavily_search(f"{company_name} github organization", max_results=3)
    for r in results:
        url = r.get("url", "")
        m = _GITHUB_PATTERN.search(url)
        if m:
            full = _clean_url(m.group(0))
            return (m.group(2).rstrip("/"), full)
    return None


def _extract_hq_from_blob(blob: str) -> Optional[str]:
    m = _HEADQUARTERS_PATTERN.search(blob)
    if not m:
        return None
    city = m.group(1)
    state = (m.group(2) or "").strip()
    if state:
        return f"{city}, {state}"
    return city


def _extract_founded_year(content: str) -> Optional[int]:
    if not content:
        return None
    for pattern in _FOUNDED_YEAR_PATTERNS:
        m = pattern.search(content)
        if m:
            try:
                yr = int(m.group(1))
                if 1900 <= yr <= 2100:
                    return yr
            except (ValueError, IndexError):
                continue
    return None


def _extract_founders(content: str) -> List[str]:
    if not content:
        return []
    found: List[str] = []
    seen: set = set()
    for pattern in _FOUNDER_PATTERNS:
        for m in pattern.finditer(content):
            raw = (m.group(1) or "").strip().rstrip(",.")
            words = raw.split()
            if len(words) > 5 or len(words) < 2:
                continue
            name = " ".join(words)
            if name[0].isupper() and name.lower() not in seen:
                seen.add(name.lower())
                found.append(name)
                if len(found) >= 4:
                    return found
    return found


def _extract_investors(content: str) -> List[str]:
    if not content:
        return []
    found: List[str] = []
    seen: set = set()
    for pattern in _INVESTOR_PATTERNS:
        for m in pattern.finditer(content):
            raw = (m.group(1) or "").strip().rstrip(",.")
            parts = re.split(r",|\band\b|\bwith\b", raw)
            for part in parts:
                part = part.strip()
                part = re.sub(r"^(the|a|an)\s+", "", part, flags=re.IGNORECASE).strip()
                if not part:
                    continue
                words = part.split()
                if len(words) > 6 or len(words) < 1:
                    continue
                if not words[0][0].isupper():
                    continue
                if part.lower() in seen:
                    continue
                seen.add(part.lower())
                found.append(part)
                if len(found) >= 6:
                    return found
    return found


def _detect_employee_bracket(content: str) -> Optional[str]:
    if not content:
        return None
    blob = content.lower()
    for lo, hi, labels in _EMPLOYEE_BRACKETS:
        for label in labels:
            if label in blob:
                return f"{lo}-{hi}"
    return None


def _detect_tech_stack(content: str) -> List[str]:
    if not content:
        return []
    haystack = content.lower()
    found: List[str] = []
    seen_canonical: set = set()
    for kw in _TECH_KEYWORDS_RAW:
        pattern = r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])"
        if re.search(pattern, haystack):
            canonical = _TECH_NORMALIZATION.get(kw, kw.title() if kw != kw.upper() else kw.upper())
            if canonical not in seen_canonical:
                seen_canonical.add(canonical)
                found.append(canonical)
    return found


def _extract_required_skills(content: str) -> List[str]:
    if not content:
        return []
    patterns = [
        re.compile(r"experience\s+(?:with|in)\s+([A-Za-z][\w.+\-#/ ]{1,40}?)(?:\s*(?:,|and|\.|;|\brequired\b|\bpreferred\b))", re.IGNORECASE),
        re.compile(r"knowledge\s+of\s+([A-Za-z][\w.+\-#/ ]{1,40}?)(?:\s*(?:,|and|\.|;|\brequired\b))", re.IGNORECASE),
        re.compile(r"familiar(?:ity)?\s+with\s+([A-Za-z][\w.+\-#/ ]{1,40}?)(?:\s*(?:,|and|\.|;))", re.IGNORECASE),
    ]
    raw: List[str] = []
    seen: set = set()
    for p in patterns:
        for m in p.finditer(content):
            phrase = (m.group(1) or "").strip().rstrip(",.;:")
            words = phrase.split()
            if len(words) > 5:
                continue
            phrase = " ".join(words)
            lookup = phrase.lower().strip()
            canonical = _TECH_NORMALIZATION.get(lookup, phrase)
            if canonical not in seen:
                seen.add(canonical)
                raw.append(canonical)
            if len(raw) >= 10:
                break
    return raw


def _classify_work_mode(careers_content: str, funding_content: str = "") -> str:
    haystack = (careers_content or "") + "\n" + (funding_content or "")
    if any(p.search(haystack) for p in _ONSITE_PATTERNS):
        return "onsite"
    if any(p.search(haystack) for p in _REMOTE_PATTERNS):
        return "remote"
    if any(p.search(haystack) for p in _HYBRID_PATTERNS):
        return "hybrid"
    return "unknown"


def _classify_hiring(careers_content: str, funding_content: str = "") -> str:
    blob = (careers_content or "") + "\n" + (funding_content or "")
    if re.search(r"\bactively\s+hiring\b", blob, re.IGNORECASE):
        return "actively_hiring"
    if re.search(r"\bwe'?re\s+hiring\b", blob, re.IGNORECASE):
        return "actively_hiring"
    if re.search(r"\bnow\s+hiring\b", blob, re.IGNORECASE):
        return "actively_hiring"
    if re.search(r"\bhiring\b", blob, re.IGNORECASE):
        return "hiring"
    if re.search(r"\bjob\s+(?:opening|board)s?\b", blob, re.IGNORECASE):
        return "hiring"
    if careers_content:
        return "not_hiring"
    return "unknown"


def _extract_open_positions_count(content: str) -> Optional[int]:
    if not content:
        return None
    counts: List[int] = []
    for p in _OPEN_POSITIONS_PATTERNS:
        for m in p.finditer(content):
            try:
                v = int(m.group(1))
                if 1 <= v <= 10000:
                    counts.append(v)
            except (ValueError, IndexError):
                pass
    if not counts:
        return None
    return min(counts)


def _extract_engineering_culture_indicators(content: str) -> List[str]:
    if not content:
        return []
    found: List[str] = []
    seen: set = set()
    for label, pattern in _CULTURE_PHRASES:
        if pattern.search(content) and label not in seen:
            seen.add(label)
            found.append(label)
    return found


def _extract_departments_hiring(content: str) -> List[str]:
    if not content:
        return []
    departments = [
        "engineering", "product", "design", "research", "data",
        "marketing", "sales", "operations", "people", "finance",
        "legal", "security", "infrastructure", "data science",
        "machine learning", "ml", "ai",
    ]
    blob = content.lower()
    found: List[str] = []
    seen: set = set()
    for d in departments:
        if re.search(r"(?<![a-z])" + re.escape(d) + r"(?![a-z])", blob):
            label = "AI" if d == "ai" else d.title() if d != "ml" else "ML"
            if label not in seen:
                seen.add(label)
                found.append(label)
    return found


def _classify_experience_level(content: str) -> str:
    if not content:
        return "unknown"
    blob = content.lower()
    if "senior" in blob or "staff engineer" in blob or "principal" in blob:
        return "senior"
    if "junior" in blob or "new grad" in blob or "entry level" in blob:
        return "junior"
    if "mid-level" in blob or "intermediate" in blob:
        return "mid"
    return "unknown"


def _detect_visa_sponsorship(content: str) -> Optional[bool]:
    if not content:
        return None
    blob = content.lower()
    if "visa sponsorship" in blob or "sponsor visa" in blob or "h-1b" in blob or "h1b" in blob:
        return True
    if "no visa" in blob or "cannot sponsor" in blob or "no sponsorship" in blob:
        return False
    return None


def _detect_internship_friendly(content: str) -> Optional[bool]:
    if not content:
        return None
    blob = content.lower()
    if "intern" in blob:
        return True
    if "no interns" in blob:
        return False
    return None


def _detect_graduate_friendly(content: str) -> Optional[bool]:
    if not content:
        return None
    blob = content.lower()
    if "new grad" in blob or "recent graduate" in blob or "entry level" in blob:
        return True
    return None


def _primary_ai_domain(content: str) -> Optional[str]:
    if not content:
        return None
    blob = content.lower()
    best_label: Optional[str] = None
    best_score = 0
    for label, keywords in _INDUSTRY_AI_DOMAINS.items():
        score = sum(1 for k in keywords if k in blob)
        if score > best_score:
            best_score = score
            best_label = label
    return best_label


# ─── Per-company enrichment ───────────────────────────────────────────
def _set_if_absent(company: Dict[str, Any], key: str, value: Any) -> None:
    """Set ``company[key] = value`` ONLY if not already populated.

    Never overwrites a non-empty existing value. Used by every
    enrichment field so existing populated data is preserved verbatim.
    """
    if value is None:
        return
    if value == "":
        return
    if isinstance(value, (list, dict)) and len(value) == 0:
        return
    if not company.get(key):
        company[key] = value


def enrich_company(company: Dict[str, Any], timeout_per_call: float = 6.0) -> Dict[str, Any]:
    """Run all enrichment lookups for a single company in parallel.

    Updates the dict in-place with NEW fields only. Existing populated
    fields are preserved verbatim (``_set_if_absent`` is the gate).

    Returns the same dict for chaining. Safe to call repeatedly.
    No LLM calls — every field is best-effort from public web APIs.
    """
    name = (company.get("name") or "").strip()
    if not name:
        return company

    funding_content_initial = (
        company.get("why_hot", "") + "\n" + company.get("tagline", "")
    )
    source_url = company.get("website", "")

    def _safe(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            return None

    results: Dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        # Sprint 3: company-website discovery needs the funding article
        # host so it can exclude the article URL from candidate set.
        funding_article_host = ""
        if source_url:
            funding_article_host = _normalize_host(source_url)

        futures: Dict[str, Any] = {
            "company_website_result": pool.submit(
                _find_company_website, name, funding_article_host, ""
            ),
            "linkedin_url": pool.submit(_find_linkedin, name),
            "github_org": pool.submit(_find_github_org, name),
        }
        funding_content_full = ""
        if source_url:
            futures["funding_content_full"] = pool.submit(
                _firecrawl_scrape, source_url, timeout_per_call
            )
        else:
            futures["funding_content_full"] = None

        for key, fut in futures.items():
            if fut is None:
                continue
            try:
                results[key] = fut.result(timeout=timeout_per_call)
            except Exception:
                results[key] = None

        funding_content_full = results.get("funding_content_full") or ""

        # Re-run company-website discovery with the full article
        # content (Firecrawl markdown) so canonical-tag and
        # body-mention signals are available.
        try:
            website_result = _find_company_website(
                name,
                funding_article_host,
                funding_content_full,
            )
        except Exception:
            website_result = {
                "website": None,
                "confidence": 0.0,
                "source": "error",
            }

    # Persist company website + provenance. Never overwrite.
    if website_result.get("website"):
        _set_if_absent(company, "company_website", website_result["website"])
        _set_if_absent(
            company, "website_confidence", website_result["confidence"]
        )
        _set_if_absent(company, "website_source", website_result["source"])
    else:
        _set_if_absent(company, "company_website", None)
        _set_if_absent(company, "website_confidence", 0.0)
        _set_if_absent(company, "website_source", website_result.get("source", ""))

    _set_if_absent(company, "linkedin_url", results.get("linkedin_url"))

    github = results.get("github_org")
    if github:
        _set_if_absent(company, "github_org", github[0])
        _set_if_absent(company, "github_url", github[1])
    else:
        _set_if_absent(company, "github_org", None)
        _set_if_absent(company, "github_url", None)

    # Sprint 3: careers page with confidence + verification.
    try:
        careers_result = _find_careers_page(
            name,
            website_result.get("website") or "",
            funding_content_full,
        )
    except Exception:
        careers_result = {"url": None, "confidence": 0.0, "source": "error"}

    careers_page = careers_result.get("url")
    _set_if_absent(company, "careers_page_url", careers_page)
    _set_if_absent(company, "careers_confidence", careers_result.get("confidence", 0.0))
    _set_if_absent(company, "careers_source", careers_result.get("source", ""))

    # Application URL defaults to careers page if found, else website.
    if careers_page:
        _set_if_absent(company, "application_url", careers_page)
    elif website_result.get("website"):
        _set_if_absent(company, "application_url", website_result["website"])

    careers_content = ""
    if careers_page:
        careers_content = _safe(_firecrawl_scrape, careers_page, timeout_per_call)

    funding_content_full = (results.get("funding_content_full") or "") + "\n" + careers_content
    blob = funding_content_initial + "\n" + funding_content_full

    _set_if_absent(company, "headquarters", _safe(_extract_hq_from_blob, blob))
    _set_if_absent(company, "founded_year_int", _safe(_extract_founded_year, blob))
    _set_if_absent(company, "founders", _safe(_extract_founders, blob) or [])
    _set_if_absent(company, "employee_count_bracket", _safe(_detect_employee_bracket, blob))
    _set_if_absent(company, "investors", _safe(_extract_investors, blob) or [])

    _set_if_absent(company, "hiring_status_detailed", _safe(_classify_hiring, blob) or "unknown")
    _set_if_absent(company, "work_mode", _safe(_classify_work_mode, blob) or "unknown")
    _set_if_absent(company, "primary_ai_domain", _safe(_primary_ai_domain, blob))

    tech = _safe(_detect_tech_stack, careers_content) or _safe(_detect_tech_stack, funding_content_full)
    _set_if_absent(company, "tech_stack", tech or [])

    _set_if_absent(company, "required_skills", _safe(_extract_required_skills, careers_content) or [])
    _set_if_absent(company, "departments_hiring", _safe(_extract_departments_hiring, blob) or [])
    _set_if_absent(company, "open_positions_count", _safe(_extract_open_positions_count, blob))
    _set_if_absent(company, "engineering_culture_indicators", _safe(_extract_engineering_culture_indicators, blob) or [])
    _set_if_absent(company, "preferred_experience_level", _safe(_classify_experience_level, blob) or "unknown")
    _set_if_absent(company, "visa_sponsorship_mentioned", _safe(_detect_visa_sponsorship, blob))
    _set_if_absent(company, "graduate_friendly", _safe(_detect_graduate_friendly, blob))
    _set_if_absent(company, "internship_friendly", _safe(_detect_internship_friendly, blob))

    work_mode = company.get("work_mode") or "unknown"
    if work_mode == "remote":
        company["remote_friendly"] = True
    elif work_mode in ("onsite", "hybrid"):
        company["remote_friendly"] = False
    else:
        company.setdefault("remote_friendly", None)

    _set_if_absent(company, "application_url", careers_page or company.get("company_website"))
    _set_if_absent(company, "last_funding_announcement_url", source_url or None)
    company.setdefault("discovery_timestamp", datetime.now(timezone.utc).isoformat())
    company["enriched_at"] = datetime.now(timezone.utc).isoformat()

    high_value_fields = [
        "company_website", "linkedin_url", "github_org", "careers_page_url",
        "founded_year_int", "founders", "employee_count_bracket",
        "investors", "hiring_status_detailed", "work_mode",
        "primary_ai_domain", "tech_stack", "required_skills",
        "departments_hiring", "open_positions_count",
    ]
    filled = sum(1 for f in high_value_fields if company.get(f))
    company["enrichment_confidence"] = round(filled / len(high_value_fields), 2)
    company["enrichment_status"] = (
        "enriched" if company["enrichment_confidence"] >= 0.5
        else "partial" if company["enrichment_confidence"] >= 0.2
        else "skipped"
    )
    return company


# ─── Top-level entry point ─────────────────────────────────────────────
def run_enrichment(force: bool = False, ttl_days: int = 6) -> Dict[str, Any]:
    """Read the cache, enrich every company, write the cache back.

    The TTL optimization skips a company whose ``enrichment_confidence``
    is already ≥ 0.7 AND whose ``enriched_at`` is within ``ttl_days``.
    Set ``force=True`` to bypass the TTL (used by the manual admin
    endpoint and by the post-discovery auto-trigger).

    The cache file is the synchronization point, so concurrent calls
    with ``_load_companies`` are safe.
    """
    from app.services.orchestrator import _CACHE_PATH, _read_cache, _write_cache

    cached = _read_cache()
    if cached is None:
        return {"status": "error", "reason": "no cache", "enriched": 0}

    companies = cached.get("companies") if isinstance(cached, dict) else cached
    if not isinstance(companies, list):
        return {"status": "error", "reason": "cache shape", "enriched": 0}

    enriched_count = 0
    skipped_count = 0
    now = datetime.now(timezone.utc)
    for company in companies:
        if not isinstance(company, dict):
            continue
        if not force:
            last_enriched = company.get("enriched_at")
            last_conf = company.get("enrichment_confidence") or 0
            if last_enriched and last_conf >= 0.7:
                try:
                    dt = datetime.fromisoformat(last_enriched.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    age_days = (now - dt).days
                    if age_days < ttl_days:
                        skipped_count += 1
                        continue
                except Exception:
                    pass
        try:
            enrich_company(company)
            enriched_count += 1
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Enrichment failed for %s: %s", company.get("name"), exc)

    try:
        _write_cache(cached if isinstance(cached, dict) else companies)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Cache writeback failed: %s", exc)
        return {
            "status": "error",
            "reason": "writeback failed",
            "enriched": enriched_count,
            "error": str(exc),
        }

    return {
        "status": "ok",
        "enriched": enriched_count,
        "skipped": skipped_count,
        "total": len(companies),
    }
