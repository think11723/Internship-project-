"""Sprint 9 — RSS-based discovery (replaces Tavily).

Pulls articles from a small set of free, public RSS feeds that
regularly publish AI-startup funding news, then merges, deduplicates,
and date-filters the results. No API keys required.

Feeds:
  - Google News RSS  (queries for "AI startup funding")
  - TechCrunch Startups RSS
  - Hacker News "front page" RSS

Discovery flow (per call):
  1. Fetch all feeds in parallel (httpx + feedparser).
  2. Normalise to a common schema (title, url, content, published_date,
     source_feed).
  3. Deduplicate on URL (strip query string + fragment).
  4. Filter to articles whose published_date is within
     ``[window_start, window_end]``. Articles without a parseable date
     are kept only if the publish date is missing AND the title looks
     like a funding article — otherwise dropped (Sprint 1 rule).
  5. Sort by published_date descending.
  6. Cap at ``MAX_FINAL_COMPANIES``.

If every feed fails, the caller gets an empty list and is expected
to handle that as a discovery failure (preserve existing cache /
initialise from seed).
"""
from __future__ import annotations

import html
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit, urlunsplit

try:
    import feedparser  # type: ignore
    _HAS_FEEDPARSER = True
except ImportError:
    feedparser = None  # type: ignore
    _HAS_FEEDPARSER = False

logger = logging.getLogger("fundflow.rss")


# Default feeds. All free. No API keys.
DEFAULT_FEEDS: List[Dict[str, str]] = [
    {
        "name": "google_news_ai_funding",
        "url": (
            "https://news.google.com/rss/search?q=%22AI+startup%22+"
            "funding+when%3A7d&hl=en-US&gl=US&ceid=US:en"
        ),
    },
    {
        "name": "techcrunch_startups",
        "url": "https://techcrunch.com/category/startups/feed/",
    },
    {
        "name": "hackernews_front",
        "url": "https://hnrss.org/frontpage",
    },
]

MAX_FEED_ENTRIES = 50         # per feed
MAX_FINAL_ARTICLES = 60        # per call

# Heuristic: a "funding article" should contain at least one of these.
_FUNDING_KEYWORDS = re.compile(
    r"\b("
    r"raises|raised|raise|funding|funded|investment|invests|"
    r"secures|secured|closes|closed|nabs|nabbed|lands|landed|"
    r"bags|bagged|hauls|hauled|scores|scored|series\s+[a-f]|"
    r"seed|venture|valuation|capital|backed|led\s+by|"
    r"acquires|acquired|acquisition"
    r")\b",
    re.IGNORECASE,
)


# ─── Helpers ───────────────────────────────────────────────────────────────

def _normalise_url(url: str) -> str:
    """Strip tracking query parameters and fragment. Used for dedup.

    Lowercases the host and scheme so the same article served via
    ``https://Example.com/...`` and ``HTTPS://example.com/...`` dedupes
    together.
    """
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
    except Exception:
        return url
    scheme = (parts.scheme or "").lower()
    netloc = (parts.netloc or "").lower()
    return urlunsplit((scheme, netloc, parts.path, "", ""))


def _parse_published(entry: Dict[str, Any]) -> Optional[str]:
    """Return an ISO-8601 UTC string or None."""
    # feedparser exposes a time.struct_time in entry.published_parsed
    # AND a raw string in entry.published.
    pp = entry.get("published_parsed")
    if pp:
        try:
            dt = datetime(*pp[:6], tzinfo=timezone.utc)
            return dt.date().isoformat()
        except Exception:
            pass
    raw = entry.get("published")
    if raw:
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.date().isoformat()
        except Exception:
            return None
    return None


def _within_window(iso_date: Optional[str], window_start: str, window_end: str) -> bool:
    if not iso_date:
        return False
    try:
        d = datetime.fromisoformat(iso_date).date()
        ws = datetime.fromisoformat(window_start).date()
        we = datetime.fromisoformat(window_end).date()
    except Exception:
        return False
    return ws <= d <= we


def _is_funding_article(title: str, summary: str) -> bool:
    blob = f"{title}\n{summary}"
    return bool(_FUNDING_KEYWORDS.search(blob))


def _feed_to_articles(parsed: Any, source_name: str) -> List[Dict[str, Any]]:
    """Convert a feedparser result into normalised article dicts.

    Sprint 13.7 — Production Stabilization — Data Quality:
      Decodes HTML entities in titles, summaries, and links so the
      deterministic extractor never sees raw ``&nbsp;``,
      ``&quot;``, ``&ldquo;``, ``&rdquo;``, ``&#39;``, ``&amp;``.
      Also normalises curly quotes to straight ASCII so the cache
      and API JSON never carry Unicode quote characters that React
      may mishandle in the UI.

    Uses the canonical ``_decode_html_entities`` from the
    deterministic extractor module so both stages share the same
    entity-decoding + Unicode-whitespace-normalisation rules.
    """
    from app.services._deterministic_extractor import (
        _decode_html_entities as _decode,
    )

    out: List[Dict[str, Any]] = []
    for entry in parsed.entries[:MAX_FEED_ENTRIES]:
        title = _decode((entry.get("title") or "").strip())
        link = _decode((entry.get("link") or "").strip())
        if not title or not link:
            continue
        summary = _decode(
            (entry.get("summary")
             or entry.get("description")
             or entry.get("subtitle")
             or "").strip()
        )
        # Strip basic HTML from summary.
        summary = re.sub(r"<[^>]+>", " ", summary).strip()
        summary = re.sub(r"\s+", " ", summary)[:1500]
        published = _parse_published(entry)
        out.append({
            "title": title,
            "url": link,
            "content": summary,
            "published_date": published,
            "source_feed": source_name,
        })
    return out


# ─── Public entry point ───────────────────────────────────────────────────

def fetch_feed(url: str, source_name: str) -> List[Dict[str, Any]]:
    """Fetch + parse a single RSS feed. Returns [] on any failure."""
    if not _HAS_FEEDPARSER:
        logger.warning("feedparser not installed; RSS discovery unavailable")
        return []
    try:
        import httpx
        with httpx.Client(timeout=httpx.Timeout(10.0, connect=3.0)) as client:
            r = client.get(url, follow_redirects=True)
            r.raise_for_status()
            raw = r.text
    except Exception as exc:
        logger.warning("RSS fetch failed for %s (%s): %s", source_name, url, exc)
        return []
    try:
        parsed = feedparser.parse(raw)
    except Exception as exc:
        logger.warning("RSS parse failed for %s: %s", source_name, exc)
        return []
    return _feed_to_articles(parsed, source_name)


def discover_articles(
    window_start: str,
    window_end: str,
    feeds: Optional[List[Dict[str, str]]] = None,
) -> List[Dict[str, Any]]:
    """Discover funding articles within ``[window_start, window_end]``.

    Returns a list of normalised dicts sorted by published_date DESC,
    capped at ``MAX_FINAL_ARTICLES``. Feeds that fail are silently
    skipped — the pipeline continues with whatever is available.
    """
    feeds = feeds or DEFAULT_FEEDS
    all_articles: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=len(feeds)) as pool:
        futures = {
            pool.submit(fetch_feed, feed["url"], feed["name"]): feed
            for feed in feeds
        }
        for fut in futures:
            try:
                all_articles.extend(fut.result(timeout=15.0))
            except Exception as exc:
                logger.warning("RSS worker raised: %s", exc)

    # Deduplicate on normalised URL.
    seen: set = set()
    deduped: List[Dict[str, Any]] = []
    for art in all_articles:
        key = _normalise_url(art["url"])
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(art)

    # Date filter. Articles without a parseable date are dropped
    # (strict window — same rule as the previous Tavily path).
    in_window = [
        a for a in deduped
        if _within_window(a.get("published_date"), window_start, window_end)
    ]

    # Sort newest first.
    in_window.sort(
        key=lambda a: (a.get("published_date") or "", a.get("title") or ""),
        reverse=True,
    )
    return in_window[:MAX_FINAL_ARTICLES]
