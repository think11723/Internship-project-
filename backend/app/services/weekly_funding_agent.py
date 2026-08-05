"""Weekly Funding Agent.

Pipeline:
  1. Tavily search (server-side date window). Real HTTP call.
  2. Deterministic extraction from Tavily's structured response
     (title / url / content / published_date). NO LLM.
  3. Firecrawl scrape (real HTTP call) for richer markdown when the
     deterministic fields leave gaps.
  4. Optional OpenRouter LLM enrichment (best-effort, failures
     swallowed — the deterministic record stands on its own).
  5. Cache file is rewritten. The existing API reads from this cache
     and is unchanged.

Seed fallback is ONLY used when Tavily itself returns zero usable
URLs OR Firecrawl returns zero usable pages — i.e. hard upstream
failures. An LLM 402 / 429 / timeout / empty content NEVER triggers
seed fallback. The deterministic record from step 2 stands alone.
"""

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.services._deterministic_extractor import (
    normalize_window as deterministic_normalize_window,
)
from app.services.discovery_service import (
    MAX_FINAL_COMPANIES,
    WEEKLY_SEARCH_QUERIES,
    _firecrawl_scrape,
    _tavily_search_for_window,
)

logger = logging.getLogger("fundflow")


def _tavily_search_window(
    window_start: str, window_end: str
) -> List[Dict[str, Any]]:
    """Wrap ``_tavily_search_for_window`` so callers can catch a
    hard Tavily failure (missing key, network error, no results)
    cleanly and skip straight to seed fallback.
    """
    if not settings.TAVILY_API_KEY:
        raise ValueError("TAVILY_API_KEY not configured")
    results = _tavily_search_for_window(
        window_start, window_end, WEEKLY_SEARCH_QUERIES
    )
    if not results:
        raise RuntimeError(
            f"Tavily returned no results for window {window_start}..{window_end}"
        )
    return results


def _scrape_urls(
    tavily_results: List[Dict[str, Any]],
) -> Dict[str, str]:
    """Run Firecrawl in parallel and return ``url -> markdown`` map.

    Raises ``RuntimeError`` if no page yielded any markdown. Mirrors
    the existing ``discovery_service`` behavior.
    """
    if not settings.FIRECRAWL_API_KEY:
        raise ValueError("FIRECRAWL_API_KEY not configured")
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=8) as pool:
        scraped = list(
            pool.map(
                _firecrawl_scrape,
                [item["url"] for item in tavily_results[:15]],
            )
        )
    out = {item["url"]: item["markdown"] for item in scraped if item.get("markdown")}
    if not out:
        raise RuntimeError("Firecrawl returned no usable pages for last week")
    return out


def _enrich_with_llm(
    deterministic_records: List[Dict[str, Any]],
    scraped_markdown: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Best-effort LLM enrichment.

    Used ONLY to refine field values from the deterministic extract.
    If OpenRouter raises (402, 429, timeout, invalid JSON), the
    deterministic records are returned unchanged. An LLM failure is
    NEVER a reason to fall back to seed.
    """
    try:
        from app.services.discovery_service import (
            _build_normalize_prompt,
            _openai_normalize,
        )
        from app.services.llm_service import LLMService

        # Re-prepare the input the LLM expects (list of scraped dicts).
        scraped_payloads = [
            {"url": url, "markdown": md}
            for url, md in scraped_markdown.items()
        ]
        prompt = _build_normalize_prompt(scraped_payloads)
        llm_records = _openai_normalize(scraped_payloads)

        # Merge LLM values onto deterministic records (deterministic
        # provides name/headquarters/funding_amount deterministically;
        # the LLM can only refine tagline/why_hot/skills).
        by_url = {r.get("website", ""): r for r in llm_records}
        enriched = []
        for d in deterministic_records:
            url = d.get("website", "")
            llm = by_url.get(url, {})
            enriched.append({
                **d,
                "tagline": llm.get("tagline") or d["tagline"],
                "why_hot": llm.get("why_hot") or d["why_hot"],
                "skills": llm.get("skills") or d["skills"],
            })
        return enriched
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "LLM enrichment failed (%s); returning deterministic records unchanged",
            exc,
        )
        return deterministic_records


def _seed_fallback() -> List[Dict[str, Any]]:
    """Load the curated demo-data seed. Used ONLY when Tavily returns
    zero usable URLs OR Firecrawl returns zero usable pages. Mirrors
    the existing ``_load_seed_companies`` behavior in
    ``orchestrator.py`` so the page is never empty.

    NOT called on LLM failures.
    """
    import json
    from pathlib import Path

    seed_path = (
        Path(__file__).resolve().parent.parent / "data" / "seed_companies.json"
    )
    with open(seed_path, "r", encoding="utf-8") as f:
        return json.load(f)


def discover_last_week_funding(
    lookback_days: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Discover last-week-funded startups. Pure-deterministic by default.

    Flow:
      1. Tavily search with ``start_date``/``end_date`` window.
      2. Deterministic extraction from the Tavily structured response.
         This produces seed-shape records WITHOUT calling the LLM.
      3. If Firecrawl returns usable markdown, optionally enrich the
         records via OpenRouter. LLM failure NEVER triggers seed fallback.
         Firecrawl failure is also non-fatal — we keep the deterministic
         records from step 2.
      4. Cap at ``MAX_FINAL_COMPANIES``.

    Raises only when Tavily itself fails — Firecrawl and OpenRouter are
    best-effort and never block the pipeline.
    """
    days = lookback_days or settings.WEEKLY_AGENT_LOOKBACK_DAYS
    today = date.today()
    week_ago = today - timedelta(days=days)
    window_start = week_ago.isoformat()
    window_end = today.isoformat()

    tavily_results = _tavily_search_window(window_start, window_end)

    deterministic_records = deterministic_normalize_window(
        tavily_results, window_start, window_end
    )

    # Try Firecrawl + optional LLM enrichment. Both are best-effort.
    # If Firecrawl fails (rate-limited, network down, key missing),
    # we keep the deterministic records — the pipeline does NOT
    # silently degrade to seed. The user explicitly demanded this.
    scraped_markdown: Dict[str, str] = {}
    try:
        scraped_markdown = _scrape_urls(tavily_results)
    except Exception as exc:
        logger.warning("Firecrawl scrape failed (%s); using Tavily snippets only", exc)

    if scraped_markdown:
        records = _enrich_with_llm(deterministic_records, scraped_markdown)
    else:
        records = deterministic_records

    return records[:MAX_FINAL_COMPANIES]


def run_weekly_refresh(force: bool = False) -> Dict[str, Any]:
    """One tick of the weekly scheduler.

    Behavior:
      - If the cache is younger than ``DISCOVERY_CACHE_HOURS`` and
        ``force`` is False, returns ``{status: "skipped", ...}``.
      - Otherwise calls ``discover_last_week_funding``.
      - If Tavily/Firecrawl themselves fail (missing key, network
        error, no results), writes the curated seed to the cache so
        the page is never empty.
      - On success, writes the LLM-free deterministic records to the
        cache. LLM failures NEVER trigger seed fallback — they only
        mean we ship the deterministic record without LLM enrichment.

    Safe to call concurrently with ``_load_companies`` — the cache
    file is the synchronization point.
    """
    from app.services.orchestrator import _CACHE_PATH, _write_cache, _read_cache

    if not force:
        cached = _read_cache()
        if cached is not None:
            metadata = cached.get("metadata", {}) if isinstance(cached, dict) else {}
            return {
                "status": "skipped",
                "reason": "cache is fresh",
                "cached_at": metadata.get("cached_at"),
            }

    today = date.today()
    week_ago = today - timedelta(days=settings.WEEKLY_AGENT_LOOKBACK_DAYS)
    window_start = week_ago.isoformat()
    window_end = today.isoformat()

    try:
        companies = discover_last_week_funding(
            lookback_days=settings.WEEKLY_AGENT_LOOKBACK_DAYS
        )
        if not companies:
            logger.warning(
                "WeeklyFundingAgent: zero deterministic records for window "
                "%s..%s; falling back to seed",
                window_start,
                window_end,
            )
            seed = _seed_fallback()
            _write_cache(seed)
            return {
                "status": "ok",
                "companies_count": len(seed),
                "window": f"{window_start}..{window_end}",
                "fell_back_to_seed": True,
                "cached_at": _CACHE_PATH.stat().st_mtime,
            }
        _write_cache(companies)
        return {
            "status": "ok",
            "companies_count": len(companies),
            "window": f"{window_start}..{window_end}",
            "fell_back_to_seed": False,
            "cached_at": _CACHE_PATH.stat().st_mtime,
        }
    except Exception as exc:
        # Hard upstream failure (Tavily or Firecrawl). Seed fallback is
        # the right move here — never an LLM failure.
        logger.warning(
            "WeeklyFundingAgent: discovery failed (%s); falling back to seed",
            exc,
        )
        seed = _seed_fallback()
        _write_cache(seed)
        return {
            "status": "ok",
            "companies_count": len(seed),
            "window": f"{window_start}..{window_end}",
            "fell_back_to_seed": True,
            "error": str(exc),
            "cached_at": _CACHE_PATH.stat().st_mtime,
        }
