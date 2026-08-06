"""Sprint 9 — Article extraction (replaces Firecrawl).

Trafilatura is the primary extractor (fast, accurate, no JS
required). If Trafilatura fails or returns an empty result, fall back
to ``newspaper4k`` (full-text extraction with article heuristics).

If both fail, return an empty string. Callers should treat empty
strings as "this article was unparseable" and skip it — never
abort the wider pipeline over a single failed extraction.

No API keys. No remote services. Pure open-source.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

try:
    import trafilatura  # type: ignore
    _HAS_TRAFILATURA = True
except ImportError:
    trafilatura = None  # type: ignore
    _HAS_TRAFILATURA = False

try:
    from newspaper import Article as _NewspaperArticle  # type: ignore
    _HAS_NEWSPAPER = True
except ImportError:
    _NewspaperArticle = None  # type: ignore
    _HAS_NEWSPAPER = False

logger = logging.getLogger("fundflow.article_extractor")


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean_text(md_or_html: str) -> str:
    """Strip HTML tags + collapse whitespace."""
    if not md_or_html:
        return ""
    text = _HTML_TAG_RE.sub(" ", md_or_html)
    text = _WS_RE.sub(" ", text)
    return text.strip()


def _try_trafilatura(url: str) -> Optional[str]:
    """Best-effort Trafilatura extraction. Returns None on import /
    fetch / parse failure."""
    if not _HAS_TRAFILATURA or trafilatura is None:
        return None
    try:
        import httpx
    except ImportError:
        return None
    try:
        with httpx.Client(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
            r = client.get(url, follow_redirects=True)
            r.raise_for_status()
            html = r.text
    except Exception as exc:
        logger.warning("Trafilatura: fetch failed (%s): %s", url, exc)
        return None
    try:
        extracted = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            favor_recall=True,
        )
    except Exception as exc:
        logger.warning("Trafilatura: parse failed (%s): %s", url, exc)
        return None
    if not extracted or not extracted.strip():
        return None
    return _clean_text(extracted)


def _try_newspaper4k(url: str) -> Optional[str]:
    """Best-effort newspaper4k extraction. Returns None on any failure."""
    if not _HAS_NEWSPAPER or _NewspaperArticle is None:
        return None
    try:
        article = _NewspaperArticle(url)
        article.download()
        article.parse()
    except Exception as exc:
        logger.warning("newspaper4k: failed (%s): %s", url, exc)
        return None
    text = (article.text or "").strip() if article else ""
    if not text:
        return None
    return _clean_text(text)


def extract_article(url: str) -> str:
    """Extract the main text of an article at ``url``.

    Tries Trafilatura first, then newspaper4k. Returns an empty
    string if both fail. Never raises.
    """
    if not url:
        return ""
    result = _try_trafilatura(url)
    if result:
        return result
    result = _try_newspaper4k(url)
    if result:
        return result
    logger.debug("extract_article: all extractors failed for %s", url)
    return ""


def extract_many(urls):
    """Best-effort batch extraction. Returns a ``{url: text}`` map
    (missing entries are failed extractions). Uses a thread pool
    so slow extractions don't block the rest of the batch.
    """
    from concurrent.futures import ThreadPoolExecutor
    out: dict = {}
    if not urls:
        return out
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(extract_article, u): u for u in urls}
        for fut in futures:
            url = futures[fut]
            try:
                out[url] = fut.result(timeout=20.0)
            except Exception:
                out[url] = ""
    return out
