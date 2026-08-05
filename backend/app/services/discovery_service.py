"""DiscoveryService - real-world company discovery.

Pipeline:
    1. Tavily web search across 5 seed queries for recently funded AI
       startups.
    2. Firecrawl scrape of the top unique URLs.
    3. OpenAI normalization into structured company records that match
       the existing seed schema (so the rest of the app does not need
       to know whether a company came from seed or live discovery).

If any step fails (missing API key, network error, etc.) the service
raises and the caller is expected to fall back to Demo Data.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

import httpx

from app.core.config import settings
from app.services.llm_service import LLMService

logger = logging.getLogger("fundflow")

SEARCH_QUERIES = [
    "recently funded AI startups",
    "Series A AI startups",
    "Series B AI startups",
    "developer tools startups",
    "enterprise AI startups",
]

SEARCH_DOMAINS = [
    "techcrunch.com",
    "crunchbase.com",
    "venturebeat.com",
    "forbes.com",
    "techstartups.com",
]

MAX_SCRAPES = 15
MAX_FINAL_COMPANIES = 20

# Network timeouts - tight enough to fail fast when an external API is
# slow, generous enough to cover a healthy round-trip.
_HTTP_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_SCRAPE_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

# Parallelism budget. External API rate limits usually cap well below
# this; the executor primarily removes sequential blocking.
_MAX_WORKERS = 8


def discover_companies_from_web() -> List[Dict[str, Any]]:
    """Run the full discovery pipeline and return normalized companies.

    Tavily queries and Firecrawl scrapes are issued **in parallel**
    (ThreadPoolExecutor) so the typical wall-clock for a successful
    run is ~10-20s instead of the previous 5-10 minutes when APIs
    are slow. Tight 10s per-call timeouts mean failure modes also
    fail fast.

    Raises:
        ValueError: if a required API key is missing.
        Exception: any underlying network / LLM failure.
    """
    if not settings.TAVILY_API_KEY:
        raise ValueError("TAVILY_API_KEY not configured")
    if not settings.FIRECRAWL_API_KEY:
        raise ValueError("FIRECRAWL_API_KEY not configured")

    search_results = _tavily_search()
    if not search_results:
        raise RuntimeError("Tavily returned no results")

    # Firecrawl scrapes run concurrently.
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        scraped = list(
            pool.map(
                _firecrawl_scrape,
                [item["url"] for item in search_results[:MAX_SCRAPES]],
            )
        )
    scraped = [item for item in scraped if item.get("markdown")]
    if not scraped:
        raise RuntimeError("Firecrawl returned no usable pages")

    companies = _openai_normalize(scraped)
    return companies[:MAX_FINAL_COMPANIES]


def _tavily_search() -> List[Dict[str, Any]]:
    """Search Tavily with each query **in parallel**, deduplicate by URL."""
    aggregated: List[Dict[str, Any]] = []
    seen_urls: set = set()

    def _fetch(query: str) -> List[Dict[str, Any]]:
        try:
            with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
                response = client.post(
                    "https://api.tavily.com/search",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {settings.TAVILY_API_KEY}",
                    },
                    json={
                        "query": query,
                        "max_results": 8,
                        "include_domains": SEARCH_DOMAINS,
                        "topic": "news",
                    },
                )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            logger.warning("Tavily query '%s' failed: %s", query, exc)
            return []
        results = []
        for result in data.get("results", []):
            url = result.get("url")
            if url:
                results.append(
                    {
                        "url": url,
                        "title": result.get("title", ""),
                        "content": result.get("content", ""),
                    }
                )
        return results

    with ThreadPoolExecutor(max_workers=len(SEARCH_QUERIES)) as pool:
        for batch in pool.map(_fetch, SEARCH_QUERIES):
            for result in batch:
                url = result.get("url")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                aggregated.append(result)

    logger.info("Tavily returned %d unique URLs", len(aggregated))
    return aggregated


def _firecrawl_scrape(url: str) -> Dict[str, Any]:
    """Scrape a single URL with Firecrawl, return markdown content."""
    try:
        with httpx.Client(timeout=_SCRAPE_TIMEOUT) as client:
            response = client.post(
                "https://api.firecrawl.dev/v1/scrape",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {settings.FIRECRAWL_API_KEY}",
                },
                json={"url": url, "formats": ["markdown"]},
            )
            response.raise_for_status()
            data = response.json()
            markdown = (
                data.get("data", {}).get("markdown")
                or data.get("markdown")
                or ""
            )
            return {"url": url, "markdown": markdown[:6000]}
    except Exception as exc:
        logger.warning("Firecrawl failed for %s: %s", url, exc)
        return {}


def _openai_normalize(scraped: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Use OpenAI chat.completions to normalize scraped content into the
    company schema used by the rest of the app.
    """
    llm = LLMService()
    prompt = _build_normalize_prompt(scraped)

    response = llm.client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a startup intelligence analyst who extracts "
                    "structured data about recently funded AI startups."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
    )

    content = ""
    if getattr(response, "choices", None):
        for choice in response.choices:
            message = getattr(choice, "message", None)
            if message is not None and getattr(message, "content", None):
                content = message.content
                break

    if not content:
        raise RuntimeError("OpenAI returned empty normalization payload")

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"OpenAI returned invalid JSON: {exc}") from exc

    companies = parsed.get("companies", [])
    if not isinstance(companies, list):
        raise RuntimeError("OpenAI payload missing 'companies' array")

    return [_normalize_company_shape(c) for c in companies]


def _normalize_company_shape(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce an LLM-normalized record into the seed schema."""
    skills = raw.get("skills") or []
    if not isinstance(skills, list):
        skills = []
    skills = [str(s).strip() for s in skills if str(s).strip()]

    return {
        "name": str(raw.get("name") or "").strip(),
        "tagline": str(raw.get("tagline") or "").strip(),
        "industry": str(raw.get("industry") or "").strip(),
        "headquarters": str(raw.get("headquarters") or "").strip(),
        "funding_round": str(raw.get("funding_round") or "").strip(),
        "funding_amount": str(raw.get("funding_amount") or "").strip(),
        "founded": str(raw.get("founded") or "").strip(),
        "career_page": str(raw.get("career_page") or "").strip(),
        "website": str(raw.get("website") or "").strip(),
        "why_hot": str(raw.get("why_hot") or "").strip(),
        "skills": skills,
    }


def _build_normalize_prompt(scraped: List[Dict[str, Any]]) -> str:
    sources = "\n\n".join(
        f"SOURCE: {item['url']}\n{item['markdown']}" for item in scraped
    )
    return (
        "Extract structured information about recently funded AI / tech startups "
        "from the sources below.\n\n"
        "Return ONLY valid JSON in this exact shape:\n"
        "{\n"
        '  "companies": [\n'
        "    {\n"
        '      "name": "Company Name",\n'
        '      "tagline": "One sentence (max 15 words)",\n'
        '      "industry": "e.g. AI Search, Developer Tools, Enterprise AI",\n'
        '      "headquarters": "City, Country",\n'
        '      "funding_round": "Series A / Series B / Seed / etc",\n'
        '      "funding_amount": "$XXM or $XXB (amount only)",\n'
        '      "founded": "YYYY or empty",\n'
        '      "career_page": "company.com/careers or jobs.company.com",\n'
        '      "website": "company.com",\n'
        '      "why_hot": "1-2 sentences on why interesting right now",\n'
        '      "skills": ["Python", "PyTorch", "AWS", ...] (5-8 skills)\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "REQUIREMENTS:\n"
        "- Return 10-20 high-quality, RECENT funding events (last ~6 months).\n"
        "- Focus on AI, developer tools, infrastructure, enterprise AI, robotics.\n"
        "- Deduplicate across sources.\n"
        "- Unknown fields use empty string, never invent.\n"
        "- Skills must be concrete technologies a candidate would actually list.\n\n"
        f"SCRAPED SOURCES:\n{sources}"
    )