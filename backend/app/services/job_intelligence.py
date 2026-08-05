"""Sprint 6 — Real Job Opening Intelligence.

Pure-deterministic scraper+parser of public careers pages. Consumes
the ``careers_page_url`` discovered in Sprint 3, fetches it via the
existing Firecrawl wrapper, and emits a structured job list + hiring
summary.

No LLM calls. No external ATS API. No OAuth. No paid services. The
scraper is a deterministic regex/keyword parser over Firecrawl's
markdown output. If the careers page can't be parsed, the function
returns empty lists — never fabricates jobs, salaries, or hiring
signals.

This module is purely additive. ``career_intelligence.generate_recommendation``
and ``application_strategy.build_application_strategy`` may consume its
output but no other code path depends on this module.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("fundflow")


# ─── Known-tech vocabulary (mirrors company_enricher._TECH_KEYWORDS_RAW) ──

_KNOWN_TECH = (
    "python", "javascript", "typescript", "go", "rust", "java", "kotlin",
    "swift", "ruby", "elixir", "scala", "c++", "c#",
    "react", "next.js", "vue", "svelte", "angular", "remix", "sveltekit",
    "node.js", "express", "nestjs", "fastapi", "django", "flask",
    "spring boot", "rails", "laravel", "phoenix", "django rest framework",
    "postgresql", "postgres", "mysql", "mariadb", "mongodb", "redis",
    "memcached", "etcd", "kafka", "rabbitmq", "nats", "pulsar", "kinesis", "sqs",
    "elasticsearch", "opensearch", "meilisearch", "algolia",
    "kubernetes", "k8s", "docker", "podman", "containerd", "helm",
    "terraform", "pulumi", "ansible", "argo cd", "flux",
    "aws", "azure", "gcp", "google cloud", "cloudflare", "vercel", "netlify",
    "graphql", "grpc", "websocket", "kafka streams",
    "spark", "flink", "hadoop", "iceberg",
    "pytorch", "tensorflow", "jax", "keras", "scikit-learn",
    "huggingface", "langchain", "langgraph", "llamaindex",
    "openai", "anthropic", "gemini", "llama",
    "rag", "vector database", "embeddings",
    "pinecone", "weaviate", "chroma", "qdrant", "milvus",
    "snowflake", "databricks", "dbt", "looker", "tableau",
    "figma",
    "crewai", "autogen", "langgraph",
    "claude", "gpt", "llm",
    "typescript", "javascript", "html", "css",
    "github actions", "circleci", "jenkins", "gitlab ci",
    "prometheus", "grafana", "datadog", "splunk",
    "stripe", "twilio", "sendgrid", "auth0", "okta",
    # AI / ML / data terms (Sprint 6: needed for real-job parsing).
    "computer vision", "nlp", "natural language processing",
    "deep learning", "machine learning", "mlops", "data science",
    "data engineering", "data analytics", "transformers",
    "reinforcement learning", "rlhf", "llm inference",
)

# Known department taxonomy.
_DEPARTMENT_PATTERNS = (
    ("Engineering", ("engineer", "developer", "backend", "frontend",
                      "full.?stack", "devops", "sre", "platform", "infrastructure",
                      "mobile", "ios", "android", "embedded", "systems",
                      "software", "cloud", "site reliability", "data engineer")),
    ("ML / Data",   ("ml engineer", "machine learning", "data scientist",
                      "data engineer", "data analyst", "research",
                      "applied scientist", "ai engineer", "mlops",
                      "research engineer", "applied ml", "analytics")),
    ("Product",     ("product manager", "product designer", "ux",
                      "ui designer", "design", "product")),
    ("GTM",         ("marketing", "sales", "growth", "demand gen",
                      "revenue", "account executive", "partnerships",
                      "customer success", "sales engineer", "go.?to.?market",
                      "bd", "business development", "content marketing")),
    ("Operations",  ("operations", "people", "recruiter", "people ops",
                      "finance", "legal", "people partner", "talent",
                      "office", "it", "security", "compliance", "hr")),
)

# Section delimiter — Greenhouse boards-style pages separate jobs with
# horizontal rules or empty lines between role headings.
_JOB_SPLIT_RE = re.compile(r"(?:\n\s*[-=*]{3,}\s*\n|\n{3,})")

# Heading patterns. Markdown produced by Firecrawl typically uses
# `# Title`, `## Title`, `### Title`. Some Greenhouse pages use
# `<strong>Title</strong>` (which becomes `**Title**` in markdown).
_HEADING_RE = re.compile(r"^#{1,3}\s+(.+?)\s*$", re.MULTILINE)


# ─── Helpers ───────────────────────────────────────────────────────────────

def _split_jobs(markdown: str) -> List[str]:
    """Split a careers-page markdown into per-job chunks.

    Heuristic: each chunk starts with a markdown heading (or bold text)
    and ends at the next heading or horizontal rule. Returns the raw
    text of each chunk.
    """
    if not markdown:
        return []

    # Find all heading positions.
    matches = list(_HEADING_RE.finditer(markdown))
    if not matches:
        # Fall back to splitting on double newlines.
        return [c.strip() for c in _JOB_SPLIT_RE.split(markdown) if c.strip()]

    chunks: List[str] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        chunk = markdown[start:end].strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def _extract_title(chunk: str) -> Optional[str]:
    """Extract the job title from the first heading of a chunk."""
    m = _HEADING_RE.search(chunk)
    if m:
        title = m.group(1).strip()
        # Strip trailing markdown decoration.
        title = title.strip("*_").strip()
        if title:
            return title
    # Fallback: first non-empty line.
    for line in chunk.splitlines():
        s = line.strip().strip("*_")
        if s and len(s) < 120:
            return s
    return None


def _classify_department(title: str, chunk: str) -> str:
    """Return the most-likely department from the title + chunk."""
    haystack = f"{title or ''} {chunk}".lower()
    best_dept, best_hits = "Other", 0
    for dept, keywords in _DEPARTMENT_PATTERNS:
        hits = sum(1 for kw in keywords if kw in haystack)
        if hits > best_hits:
            best_dept, best_hits = dept, hits
    return best_dept


def _extract_location(chunk: str) -> Optional[str]:
    """Best-effort location extraction."""
    # Greenhouse-style: "Location: New York, NY" or "Remote / New York".
    m = re.search(
        r"(?:location|based in|where)\s*[:\-]?\s*"
        r"([A-Z][A-Za-z .,'/\-]{2,60})",
        chunk,
    )
    if m:
        loc = m.group(1).strip().rstrip(",.")
        # Filter out lines that look like job requirements.
        if "year" not in loc.lower() and "experience" not in loc.lower():
            return loc

    # Remote / Hybrid / Onsite.
    for word in ("Remote", "Hybrid", "Onsite", "On-site"):
        if re.search(rf"\b{word}\b", chunk):
            return word

    # City, ST pattern.
    m = re.search(r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)?),\s*([A-Z]{2})\b", chunk)
    if m:
        return f"{m.group(1)}, {m.group(2)}"

    return None


def _extract_experience(chunk: str) -> Optional[str]:
    """Extract years-of-experience phrase."""
    # "3+ years", "3-5 years", "5+ years of experience", "at least 2 years".
    m = re.search(
        r"(\d+\+?\s*(?:[-–]\s*\d+\s*)?\s*years?\s*(?:of\s+)?(?:experience|exp)?)",
        chunk,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    if re.search(r"\b(entry[\s-]level|new[\s-]grad|junior)\b", chunk, re.IGNORECASE):
        return "Entry level"
    if re.search(r"\b(senior|staff|principal)\b", chunk, re.IGNORECASE):
        return "Senior"
    if re.search(r"\b(intern|internship|co-?op)\b", chunk, re.IGNORECASE):
        return "Internship"
    return None


def _extract_employment_type(chunk: str) -> Optional[str]:
    if re.search(r"\b(internship|intern)\b", chunk, re.IGNORECASE):
        return "Internship"
    if re.search(r"\b(contract|contractor)\b", chunk, re.IGNORECASE):
        return "Contract"
    if re.search(r"\b(part[\s-]time)\b", chunk, re.IGNORECASE):
        return "Part Time"
    return "Full Time"


def _extract_skills(chunk: str) -> List[str]:
    """Extract known technologies mentioned in the chunk.

    Avoids false positives via word-boundary matching. Multi-word
    phrases (e.g. "next.js", "spring boot") are matched first.
    """
    blob = " " + chunk.lower() + " "
    found: List[str] = []
    seen_lower: set = set()
    # Sort by length desc so multi-word phrases match before substrings.
    for tech in sorted(_KNOWN_TECH, key=len, reverse=True):
        # Word-boundary match: tech is a literal phrase.
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(tech)}(?![A-Za-z0-9])", blob):
            tl = tech.lower()
            if tl not in seen_lower:
                seen_lower.add(tl)
                found.append(tech)
    return found


def _extract_nice_to_have(chunk: str, must_haves: List[str]) -> List[str]:
    """Extract skills listed under 'nice to have' / 'bonus' / 'plus'."""
    must_lower = {m.lower() for m in must_haves}
    nice: List[str] = []
    patterns = [
        r"nice\s*to\s*have[:\s]+(.*?)(?:\n\n|\Z)",
        r"bonus[:\s]+(.*?)(?:\n\n|\Z)",
        r"plus[:\s]+(.*?)(?:\n\n|\Z)",
        r"preferred\s*qualifications?[:\s]+(.*?)(?:\n\n|\Z)",
    ]
    blob = chunk
    for pat in patterns:
        m = re.search(pat, blob, re.IGNORECASE | re.DOTALL)
        if m:
            section = m.group(1)
            for tech in _extract_skills(section):
                if tech.lower() not in must_lower and tech.lower() not in {n.lower() for n in nice}:
                    nice.append(tech)
    return nice[:8]


def _extract_responsibilities(chunk: str) -> List[str]:
    """Extract bullet-point responsibilities from the chunk."""
    # Look for "Responsibilities:" or "What you'll do:" header.
    m = re.search(
        r"(?:responsibilities|what you.?ll do|you will)\s*[:\-]\s*(.*?)"
        r"(?:qualifications|requirements|about you|what we look|nice\s*to\s*have|\Z)",
        chunk,
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return []
    section = m.group(1)
    bullets: List[str] = []
    for line in section.splitlines():
        s = line.strip().lstrip("-•*").strip()
        # Filter non-bullet prose.
        if s and len(s) > 10 and not s.endswith(":") and s[0].isalpha():
            bullets.append(s)
        if len(bullets) >= 5:
            break
    return bullets


def _extract_apply_url(chunk: str, careers_url: str) -> Optional[str]:
    """Find the application URL in the chunk or fall back to careers."""
    m = re.search(r"https?://[^\s)]+(?:apply|job|position)[^\s)]*", chunk, re.IGNORECASE)
    if m:
        return m.group(0).rstrip(".,);\"'")
    # Fallback to the careers page itself.
    return careers_url or None


def _is_internship(chunk: str, title: str) -> bool:
    """Detect internship / co-op roles."""
    blob = f"{title or ''} {chunk}".lower()
    return bool(
        re.search(r"\b(intern(ship)?|co-?op)\b", blob, re.IGNORECASE)
    )


def _is_graduate_role(chunk: str, title: str) -> bool:
    """Detect new-grad / entry-level roles."""
    blob = f"{title or ''} {chunk}".lower()
    return bool(
        re.search(r"\b(new[\s-]grad(uate)?|entry[\s-]level)\b", blob, re.IGNORECASE)
    )


def _detect_visa(chunk: str) -> Optional[bool]:
    """Detect visa-sponsorship language."""
    blob = chunk.lower()
    if re.search(r"\b(visa\s*sponsor(ship)?|sponsor[s]?\s+visa|h-?1b|h1b)\b", blob):
        return True
    if re.search(r"\b(no\s+visa|cannot\s+sponsor|not\s+sponsor)\b", blob):
        return False
    return None


def _detect_remote(chunk: str) -> bool:
    """Detect remote / hybrid / onsite."""
    blob = chunk.lower()
    if re.search(r"\b(remote[\s-](?:first|only|ok|friendly)?|work\s*from\s*home|"
                 r"work\s*from\s*anywhere|fully\s*remote|100%\s*remote)\b", blob):
        return True
    if re.search(r"\b(hybrid)\b", blob):
        return True
    if re.search(r"\b(on[\s-]?site|onsite|in[\s-]?office)\b", blob):
        return True
    return False


def _salary_in_text(chunk: str) -> Optional[str]:
    """Best-effort salary extraction."""
    m = re.search(
        r"\$\s?\d{2,3}[kK](?:[,\s\-+]?\$?\d{2,3}[kK])?\s*(?:[-–/]\s*\$?\d{2,3}[kK])?",
        chunk,
    )
    if m:
        return m.group(0).strip()
    # £ / € ranges
    m = re.search(
        r"[£€]\s?\d{2,3}[kK](?:[,\s\-+]?[£€]?\d{2,3}[kK])?\s*(?:[-–/]\s*[£€]?\d{2,3}[kK])?",
        chunk,
    )
    if m:
        return m.group(0).strip()
    return None


# ─── Per-chunk job parsing ────────────────────────────────────────────────

def _parse_job_chunk(chunk: str, careers_url: str) -> Optional[Dict[str, Any]]:
    """Parse a single job-listing chunk into a structured job dict.

    Returns None if the chunk doesn't look like a job listing (no
    title, too short, or doesn't mention role-implying keywords).
    """
    if not chunk or len(chunk) < 30:
        return None

    title = _extract_title(chunk)
    if not title:
        return None

    # Reject headings that aren't role titles (very long, no role keyword).
    role_keywords = (
        "engineer", "developer", "scientist", "analyst", "designer",
        "manager", "lead", "architect", "specialist", "intern",
        "researcher", "writer", "editor", "recruiter", "marketer",
        "designer", "consultant", "associate", "head of", "director",
        "officer", "admin", "support", "advocate", "owner", "ops",
        "operator", "designer", "strategist",
    )
    blob_lower = f"{title} {chunk}".lower()
    if not any(kw in blob_lower for kw in role_keywords):
        return None

    skills = _extract_skills(chunk)
    nice_to_have = _extract_nice_to_have(chunk, skills)
    responsibilities = _extract_responsibilities(chunk)
    is_intern = _is_internship(chunk, title)
    is_grad = _is_graduate_role(chunk, title)
    location = _extract_location(chunk)
    experience = _extract_experience(chunk)
    employment_type = _extract_employment_type(chunk)
    apply_url = _extract_apply_url(chunk, careers_url)
    visa = _detect_visa(chunk)
    remote = _detect_remote(chunk)
    salary = _salary_in_text(chunk)

    # Confidence: based on how many fields we successfully parsed.
    confidence = 30  # base
    if skills:                    confidence += 15
    if responsibilities:          confidence += 10
    if location:                  confidence += 8
    if experience:                confidence += 8
    if apply_url and apply_url != careers_url: confidence += 8
    if employment_type:            confidence += 5
    if nice_to_have:              confidence += 5
    if remote:                    confidence += 3
    if visa is not None:          confidence += 4
    if salary:                    confidence += 3
    if is_intern:                 confidence += 2

    return {
        "title": title,
        "department": _classify_department(title, chunk),
        "experience": experience,
        "location": location or ("Remote" if remote else None),
        "employment_type": (
            "Internship" if is_intern else (employment_type or "Full Time")
        ),
        "skills": skills,
        "nice_to_have": nice_to_have,
        "responsibilities": responsibilities,
        "salary": salary,
        "apply_url": apply_url,
        "is_internship": is_intern,
        "is_graduate_role": is_grad,
        "visa_sponsorship": visa,
        "remote": remote,
        "confidence": min(100, confidence),
    }


# ─── Public entry points ───────────────────────────────────────────────────

def extract_jobs_from_markdown(
    markdown: str,
    careers_url: str = "",
) -> List[Dict[str, Any]]:
    """Parse Firecrawl-markdown output into a list of job listings.

    Returns an empty list if the markdown contains no parseable job
    listings. Never fabricates jobs.
    """
    if not markdown:
        return []
    chunks = _split_jobs(markdown)
    jobs: List[Dict[str, Any]] = []
    for chunk in chunks:
        job = _parse_job_chunk(chunk, careers_url)
        if job:
            jobs.append(job)
    return jobs


def summarize_hiring(jobs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate per-job flags into a hiring_summary dict."""
    total = len(jobs)
    eng = sum(1 for j in jobs if j.get("department") == "Engineering")
    ml_data = sum(1 for j in jobs if j.get("department") == "ML / Data")
    product = sum(1 for j in jobs if j.get("department") == "Product")
    gtm = sum(1 for j in jobs if j.get("department") == "GTM")
    ops = sum(1 for j in jobs if j.get("department") == "Operations")
    other = sum(1 for j in jobs if j.get("department") == "Other")
    interns = sum(1 for j in jobs if j.get("is_internship"))
    grads = sum(1 for j in jobs if j.get("is_graduate_role"))
    remote = sum(
        1 for j in jobs
        if j.get("remote") or (j.get("location") or "").lower() == "remote"
    )
    visa_yes = sum(1 for j in jobs if j.get("visa_sponsorship") is True)
    visa_no = sum(1 for j in jobs if j.get("visa_sponsorship") is False)
    return {
        "total_roles": total,
        "engineering_roles": eng,
        "ml_data_roles": ml_data,
        "product_roles": product,
        "gtm_roles": gtm,
        "operations_roles": ops,
        "other_roles": other,
        "internships": interns,
        "graduate_roles": grads,
        "remote_roles": remote,
        "visa_sponsored": visa_yes,
        "visa_not_sponsored": visa_no,
    }


def extract_job_intelligence(
    company: Dict[str, Any],
    markdown: Optional[str] = None,
) -> Dict[str, Any]:
    """Sprint 6 — public entry point.

    Returns:
        {
            "jobs":           List[Dict],
            "hiring_summary": Dict,
            "source":         str,   # "firecrawl_markdown" | "no_careers_url" | "empty"
            "confidence":     int,   # 0..100
        }

    The function NEVER fabricates jobs. If no careers URL exists, or
    the markdown can't be parsed, returns empty jobs + summary with
    confidence 0.
    """
    careers_url = (
        (company.get("enrichment") or {}).get("careers_page_url")
        or company.get("careers_page_url")
        or company.get("career_page")
        or ""
    )

    if not careers_url and not markdown:
        return {
            "jobs": [],
            "hiring_summary": summarize_hiring([]),
            "source": "no_careers_url",
            "confidence": 0,
        }

    if not markdown:
        return {
            "jobs": [],
            "hiring_summary": summarize_hiring([]),
            "source": "empty_markdown",
            "confidence": 0,
        }

    jobs = extract_jobs_from_markdown(markdown, careers_url)
    summary = summarize_hiring(jobs)

    if not jobs:
        return {
            "jobs": [],
            "hiring_summary": summary,
            "source": "no_jobs_found",
            "confidence": 0,
        }

    # Overall confidence: average of per-job confidences, floored.
    avg = sum(j.get("confidence", 0) for j in jobs) / len(jobs)
    return {
        "jobs": jobs,
        "hiring_summary": summary,
        "source": "firecrawl_markdown",
        "confidence": int(round(avg)),
    }


# ─── Integration shim used by application_strategy ────────────────────────

def derive_required_skills_from_jobs(
    jobs: List[Dict[str, Any]],
) -> Tuple[List[str], List[str]]:
    """Aggregate required + nice-to-have skills across all jobs.

    Returns (required_skills, nice_to_have_skills) deduplicated and
    sorted by frequency.
    """
    from collections import Counter

    req_counter: Counter = Counter()
    nice_counter: Counter = Counter()
    for job in jobs or []:
        for s in (job.get("skills") or []):
            req_counter[s] += 1
        for s in (job.get("nice_to_have") or []):
            nice_counter[s] += 1

    # Required ordered by frequency, dropping anything that only appears
    # as nice-to-have.
    required = [s for s, _ in req_counter.most_common() if req_counter[s] >= 1]
    # Nice-to-have: only those NOT already in required.
    nice = [
        s for s, _ in nice_counter.most_common()
        if s not in required and nice_counter[s] >= 1
    ]
    return required, nice