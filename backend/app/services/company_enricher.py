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

_NEWS_DOMAINS = {
    "techcrunch.com", "crunchbase.com", "venturebeat.com",
    "forbes.com", "techstartups.com", "linkedin.com",
    "twitter.com", "facebook.com", "reddit.com",
    "reuters.com", "bloomberg.com", "wsj.com", "nytimes.com",
    "tech.co", "yahoo.com", "github.com",
}


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


def _find_company_website(company_name: str) -> Optional[str]:
    results = _tavily_search(f"{company_name} official website", max_results=5)
    for r in results:
        url = r.get("url", "")
        if not url:
            continue
        m = _DOMAIN_PATTERN.search(url)
        if not m:
            continue
        host = m.group(1).lower()
        if any(host.endswith(d) for d in _NEWS_DOMAINS):
            continue
        if host.startswith("www."):
            host = host[4:]
        return f"https://{host}"
    return None


def _find_careers_page(company_website: str, funding_content: str = "") -> Optional[str]:
    if company_website:
        candidates = ["/careers", "/jobs", "/work-with-us", "/join-us", "/team"]
        for path in candidates:
            url = f"{company_website.rstrip('/')}{path}"
            return url
    if funding_content:
        m = re.search(
            r"(https?://[\w./-]+/(?:careers|jobs|work-with-us|join-us)(?:[/?#][\w./%-]*)?)",
            funding_content,
            re.IGNORECASE,
        )
        if m:
            return _clean_url(m.group(1))
    results = _tavily_search(f"{company_website} careers jobs", max_results=3)
    for r in results:
        url = r.get("url", "")
        if any(p in url.lower() for p in ["/careers", "/jobs", "/join", "/work"]):
            return _clean_url(url)
    return None


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
        futures = {
            "company_website": pool.submit(_find_company_website, name),
            "linkedin_url": pool.submit(_find_linkedin, name),
            "github_org": pool.submit(_find_github_org, name),
        }
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

    _set_if_absent(company, "company_website", results.get("company_website"))
    _set_if_absent(company, "linkedin_url", results.get("linkedin_url"))

    github = results.get("github_org")
    if github:
        _set_if_absent(company, "github_org", github[0])
        _set_if_absent(company, "github_url", github[1])
    else:
        _set_if_absent(company, "github_org", None)
        _set_if_absent(company, "github_url", None)

    careers_page = _safe(
        _find_careers_page,
        company.get("company_website") or "",
        funding_content_initial,
    )
    _set_if_absent(company, "careers_page_url", careers_page)

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
