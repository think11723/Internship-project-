"""Weekly Funding Agent — Sprint 9 (infrastructure migration).

Pipeline:
  1. RSS feeds (Google News + TechCrunch Startups + Hacker News)
     with server-side date filter. NO Tavily.
  2. Deterministic extraction from the RSS article dicts
     (title / url / content / published_date). NO LLM.
  3. Trafilatura (with newspaper4k fallback) for richer text when
     the RSS summary is too sparse. NO Firecrawl.
  4. Optional AIGateway LLM enrichment (best-effort, failures
     swallowed — the deterministic record stands on its own).
  5. Cache file is rewritten. The existing API reads from this cache
     and is unchanged.

Seed fallback is ONLY used when RSS discovery itself returns zero
usable articles — i.e. hard upstream failure. An LLM failure NEVER
triggers seed fallback. The deterministic record from step 2 stands
alone.
"""

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.services._deterministic_extractor import (
    normalize_window as deterministic_normalize_window,
)
from app.services.article_extractor import extract_many as extract_articles
from app.services.rss_discovery import discover_articles as rss_discover

logger = logging.getLogger("fundflow")


def _rss_search_window(
    window_start: str, window_end: str
) -> List[Dict[str, Any]]:
    """Fetch RSS articles for ``[window_start, window_end]``.

    Raises ``RuntimeError`` when zero articles are available — the
    caller treats this as a discovery failure and either preserves
    the existing cache or falls back to seed.
    """
    articles = rss_discover(window_start, window_end)
    if not articles:
        raise RuntimeError(
            f"RSS discovery returned no articles for window {window_start}..{window_end}"
        )
    return articles


def _scrape_articles(
    rss_results: List[Dict[str, Any]],
) -> Dict[str, str]:
    """Run Trafilatura (+ newspaper4k fallback) in parallel.

    Returns ``url -> article_text`` map. Always returns a dict (empty
    if every extraction failed) — never raises.
    """
    urls = [item["url"] for item in rss_results[:15] if item.get("url")]
    return extract_articles(urls)


def _enrich_with_llm(
    deterministic_records: List[Dict[str, Any]],
    scraped_markdown: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Best-effort AIGateway enrichment.

    Used ONLY to refine field values from the deterministic extract.
    If every provider fails (or the gateway is empty), the
    deterministic records are returned unchanged. An LLM failure is
    NEVER a reason to fall back to seed.
    """
    # Sprint 9.6: LLM enrichment is currently disabled — the
    # Tavily-era `_build_normalize_prompt` import was removed and
    # the deterministic records from `_deterministic_extractor` are
    # already complete. We keep the stub so the weekly refresh
    # path still tolerates a future re-enable.
    return deterministic_records


def _seed_fallback() -> List[Dict[str, Any]]:
    """Load the curated demo-data seed. Used ONLY when RSS discovery
    itself returns zero usable articles. NOT called on LLM failures.
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
      1. RSS discovery (Google News + TechCrunch + HN) with date filter.
      2. Deterministic extraction from the RSS article dicts. NO LLM.
      3. If Trafilatura extracts usable text, optionally enrich via
         AIGateway. LLM failure NEVER triggers seed fallback.
         Trafilatura failure is also non-fatal — we keep the
         deterministic records from step 2.
      4. Cap at ``MAX_FINAL_COMPANIES``.

    Raises only when RSS discovery itself fails (every feed unreachable
    AND zero usable articles). Trafilatura and AIGateway are best-effort
    and never block the pipeline.

    Sprint 13.7 — Production Stabilization — Data Quality:
      - The extracted records pass through ``filter_records`` which
        applies the pre-cache validation gate (valid company name,
        required fields, extraction score above threshold).
      - Rejected records are logged but never block the pipeline.
      - Records with ``below_quality_threshold=True`` are dropped
        inside ``deterministic_normalize_window`` so they never
        reach the cache.
    """
    # Lazy import to avoid a circular dependency at module load.
    from app.services.discovery_service import MAX_FINAL_COMPANIES

    days = lookback_days or settings.WEEKLY_AGENT_LOOKBACK_DAYS
    today = date.today()
    week_ago = today - timedelta(days=days)
    window_start = week_ago.isoformat()
    window_end = today.isoformat()

    rss_results = _rss_search_window(window_start, window_end)

    deterministic_records = deterministic_normalize_window(
        rss_results, window_start, window_end
    )

    # Try Trafilatura + optional AIGateway enrichment. Both are best-effort.
    scraped_markdown: Dict[str, str] = {}
    try:
        scraped_markdown = _scrape_articles(rss_results)
    except Exception as exc:
        logger.warning("Article extraction failed (%s); using RSS snippets only", exc)

    if scraped_markdown:
        records = _enrich_with_llm(deterministic_records, scraped_markdown)
    else:
        records = deterministic_records

    # Sprint 13.7: pre-cache validation gate. Reject records whose
    # required fields are missing, whose names fail validation, or
    # whose extraction score is below the quality threshold.
    valid, rejected = _validate_records(records)
    if rejected:
        logger.info(
            "WeeklyFundingAgent: rejected %d/%d records at validation gate",
            len(rejected),
            len(records),
        )
        for rec in rejected[:5]:  # log first 5 only
            logger.info(
                "  rejected %r: %s",
                rec.get("name"),
                rec.get("rejection_reasons"),
            )

    return valid[:MAX_FINAL_COMPANIES]


def _validate_records(
    records: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Sprint 13.7: apply ``filter_records`` (pre-cache validation
    gate) to the discovery results. Returns ``(valid, rejected)``.
    """
    from app.services._deterministic_extractor import filter_records
    return filter_records(records)


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
