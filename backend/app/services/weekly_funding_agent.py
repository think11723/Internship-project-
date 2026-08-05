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

    Behavior (Ticket-CRITICAL-1):
      - If the cache is younger than ``DISCOVERY_CACHE_HOURS`` and
        ``force`` is False, returns ``{status: "skipped", ...}``.
      - Otherwise calls ``discover_last_week_funding``.
      - On success (≥1 record returned), writes the deterministic
        records to the cache with ``data_source="live"``. The
        discovery succeeded regardless of Firecrawl or LLM enrichment
        status — those are best-effort and never block.
      - On zero records OR hard upstream failure (Tavily missing key,
        network error, no results):

          * **Branch A — no cache exists:** initialise the cache
            with the curated seed dataset and ``data_source="seed"``.
            This is acceptable because there is no real data to lose.
          * **Branch B — cache exists:** DO NOT TOUCH THE CACHE.
            The existing live (or seed) data is preserved. The
            response signals this with ``status="preserved"``.

    LLM failures NEVER trigger seed fallback — they only mean we
    ship the deterministic record without LLM enrichment.

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
                "data_source": metadata.get("data_source"),
            }

    today = date.today()
    week_ago = today - timedelta(days=settings.WEEKLY_AGENT_LOOKBACK_DAYS)
    window_start = week_ago.isoformat()
    window_end = today.isoformat()

    # Try the live discovery. Any exception is captured for the
    # response envelope; the seed-write branch below is gated by the
    # presence of an existing cache.
    companies: List[Dict[str, Any]] = []
    discovery_error: Optional[str] = None
    try:
        companies = discover_last_week_funding(
            lookback_days=settings.WEEKLY_AGENT_LOOKBACK_DAYS
        )
    except Exception as exc:
        discovery_error = str(exc)
        logger.warning(
            "WeeklyFundingAgent: discovery raised (%s); will preserve "
            "existing cache or fall back to seed only if no cache exists.",
            exc,
        )

    # ── Branch A — live discovery succeeded ────────────────────────
    if companies:
        _write_cache(
            companies,
            data_source="live",
            reason=(
                "successful Tavily + deterministic extraction for "
                f"window {window_start}..{window_end}"
            ),
        )
        return {
            "status": "ok",
            "companies_count": len(companies),
            "window": f"{window_start}..{window_end}",
            "fell_back_to_seed": False,
            "data_source": "live",
            "cached_at": _CACHE_PATH.stat().st_mtime,
        }

    # ── Live discovery returned 0 or raised ────────────────────────
    existing = _read_cache()
    if existing is not None:
        # ── Branch B — preserve existing cache ────────────────────
        metadata = existing.get("metadata", {}) if isinstance(existing, dict) else {}
        existing_source = metadata.get("data_source", "unknown")
        logger.warning(
            "WeeklyFundingAgent: discovery produced 0 records "
            "(error=%s); PRESERVING existing cache (data_source=%s, "
            "%d companies). No silent overwrite.",
            discovery_error or "no_results",
            existing_source,
            metadata.get("companies_count", 0),
        )
        return {
            "status": "preserved",
            "reason": (
                "discovery produced no records; existing cache preserved"
            ),
            "companies_count": metadata.get("companies_count", 0),
            "window": f"{window_start}..{window_end}",
            "fell_back_to_seed": False,
            "data_source": existing_source,
            "discovery_error": discovery_error,
            "cached_at": metadata.get("cached_at"),
        }

    # ── Branch C — first deployment; no cache exists ──────────────
    logger.warning(
        "WeeklyFundingAgent: first deployment with no cache; "
        "discovery failed (%s); initialising with curated seed.",
        discovery_error or "no_results",
    )
    seed = _seed_fallback()
    _write_cache(
        seed,
        data_source="seed",
        reason=(
            "first deployment: live discovery produced no records "
            f"(error={discovery_error or 'no_results'}); seeded for "
            "non-empty UI"
        ),
    )
    return {
        "status": "ok",
        "companies_count": len(seed),
        "window": f"{window_start}..{window_end}",
        "fell_back_to_seed": True,
        "data_source": "seed",
        "discovery_error": discovery_error,
        "cached_at": _CACHE_PATH.stat().st_mtime,
    }
