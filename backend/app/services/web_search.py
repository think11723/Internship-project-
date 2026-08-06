"""Sprint 9 — DuckDuckGo search (replaces Tavily Search for URL discovery).

Uses the ``ddgs`` package (the official DuckDuckGo Search Python
binding). It scrapes ``duckduckgo.com`` directly — no API key, no
rate limits (within DDG's fair-use caps), no signup.

We use it for **URL discovery only**, never for scraping. The
returned URLs are then fed to the article extractor (Trafilatura /
newspaper4k) when full text is needed.

Never scrape LinkedIn or GitHub directly — we only DISCOVER the URL
of the official company website, the careers page, the LinkedIn
company page, or the GitHub org.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("fundflow.web_search")

try:
    from ddgs import DDGS as _DDGS  # type: ignore
    _HAS_DDGS = True
except ImportError:
    _DDGS = None  # type: ignore
    _HAS_DDGS = False


def _ddg_query(query: str, max_results: int = 10, timelimit: Optional[str] = None) -> List[Dict[str, Any]]:
    """Run a single DDG query. Returns [] on any failure.

    The ``ddgs`` package replaced the older ``duckduckgo-search``; both
    share the same high-level interface.
    """
    if not _HAS_DDGS or _DDGS is None:
        return []
    try:
        with _DDGS() as ddgs:
            results = list(ddgs.text(
                query,
                max_results=max_results,
                timelimit=timelimit,
            ))
    except Exception as exc:
        logger.warning("DuckDuckGo search failed for %r: %s", query, exc)
        return []
    return results or []


# ─── Public API ─────────────────────────────────────────────────────────

def search_urls(query: str, max_results: int = 5) -> List[str]:
    """Search DuckDuckGo and return a list of result URLs (deduplicated)."""
    if not query:
        return []
    results = _ddg_query(query, max_results=max_results)
    seen: set = set()
    out: List[str] = []
    for r in results:
        url = (r.get("href") or r.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def search_company_assets(company_name: str) -> Dict[str, Optional[str]]:
    """Discover the official website, careers, LinkedIn, GitHub, and
    application URLs for a single company. Returns the first plausible
    match for each category (or None if not found).
    """
    if not company_name:
        return {
            "website": None, "careers": None, "linkedin": None,
            "github": None, "application_url": None,
        }
    out: Dict[str, Optional[str]] = {
        "website": None, "careers": None, "linkedin": None,
        "github": None, "application_url": None,
    }

    # 1. Official website — usually the first organic result.
    for url in search_urls(f"{company_name} official site", max_results=5):
        host = url.split("/")[2] if "://" in url else ""
        # Filter obvious non-company hosts at URL-discovery time.
        blocked = (
            "linkedin.com", "twitter.com", "x.com", "facebook.com",
            "youtube.com", "wikipedia.org", "crunchbase.com",
            "reddit.com", "glassdoor.com", "medium.com",
        )
        if any(b in host for b in blocked):
            continue
        out["website"] = url
        break

    # 2. Careers page — explicit query.
    for url in search_urls(f"{company_name} careers jobs", max_results=8):
        if any(token in url.lower() for token in ("/careers", "/jobs", "/join", "/work")):
            out["careers"] = url
            break

    # 3. LinkedIn company page — DISCOVER only (never scrape).
    for url in search_urls(f"{company_name} site:linkedin.com/company", max_results=5):
        if "linkedin.com/company/" in url:
            out["linkedin"] = url
            break

    # 4. GitHub organisation.
    for url in search_urls(f"{company_name} site:github.com", max_results=5):
        m = re.match(r"^https?://github\.com/([A-Za-z0-9_.\-]+)/?$", url)
        if m and m.group(1).lower() not in ("sponsors", "orgs", "settings", "topics", "trending", "collections"):
            out["github"] = url
            break

    # 5. Application URL — usually == careers page or apply subdomain.
    if out["careers"]:
        out["application_url"] = out["careers"]
    return out
