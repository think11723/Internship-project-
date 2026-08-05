"""Deterministic extraction helpers for the Weekly Funding Agent.

Pure regex + heuristic parsing. No LLM. Reads Tavily's structured
response (title, url, content, published_date) and emits records in
the same shape as ``discovery_service._normalize_company_shape``.
"""

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List


_FUNDING_AMOUNT_RE = re.compile(
    r"\$\s*([\d,.]+)\s*(million|billion|thousand|[BMK]\b|MM|B\.)?",
    re.IGNORECASE,
)

_FUNDING_ROUND_RE = re.compile(
    r"\b(pre[-\s]?seed|seed|series\s+[a-f]|bridge|ipo|debt|venture|growth|strategic)\b",
    re.IGNORECASE,
)

_LOCATION_RE = re.compile(
    r"\b([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?),\s*([A-Z]{2}|[A-Z][a-zA-Z]+)\b",
)

_FUNDING_KEYWORDS = {
    "AI Research": ["ai safety", "frontier model", "agi", "alignment", "reasoning"],
    "AI Search": ["answer engine", "search", "retrieval", "rag"],
    "AI Infrastructure": ["gpu cloud", "compute", "inference", "cloud", "data center"],
    "Developer Tools": ["developer", "code generation", "ide", "engineering"],
    "Enterprise AI": ["enterprise", "compliance", "workflow automation", "b2b"],
    "Generative AI": ["video", "image generation", "generative", "diffusion"],
    "AI Platform": ["platform", "model deployment", "mlops"],
    "Vertical AI": ["vertical", "industry-specific", "domain"],
}

_INDUSTRY_FALLBACK = "AI"


def parse_funding_amount(text: str) -> str:
    if not text:
        return ""
    m = _FUNDING_AMOUNT_RE.search(text)
    if not m:
        return ""
    raw = m.group(1).replace(",", "")
    unit = (m.group(2) or "").lower()
    try:
        value = float(raw)
    except ValueError:
        return ""
    if unit.startswith("b"):
        return f"${value}B"
    if unit.startswith("m") or unit.startswith("mm") or unit.startswith("million"):
        return f"${value}M"
    if unit.startswith("k") or unit.startswith("thousand"):
        return f"${value/1000:.1f}M"
    if value >= 100:
        return f"${value}B"
    return f"${value}M"


def parse_funding_round(text: str) -> str:
    m = _FUNDING_ROUND_RE.search(text)
    if not m:
        return ""
    raw = m.group(1).strip().lower()
    if raw.startswith("series"):
        parts = raw.split()
        if len(parts) > 1 and len(parts[-1]) == 1 and parts[-1].isalpha():
            return f"Series {parts[-1].upper()}"
        return raw.title()
    return raw.title()


def parse_headquarters(text: str) -> str:
    m = _LOCATION_RE.search(text)
    if not m:
        return ""
    return f"{m.group(1)}, {m.group(2)}"


def classify_industry(text: str) -> str:
    haystack = text.lower()
    best_label = _INDUSTRY_FALLBACK
    best_score = 0
    for label, keywords in _FUNDING_KEYWORDS.items():
        score = sum(1 for k in keywords if k in haystack)
        if score > best_score:
            best_score = score
            best_label = label
    return best_label


def extract_name_from_title(title: str) -> str:
    """Pull a company name out of a TechCrunch-style headline.

    Examples:
        "Dili raises $21.7 million to bring AI compliance ..." -> "Dili"
        "Index Ventures raises $2B across three funds" -> "Index Ventures"
        "Horizon3 hits $2B Series E" -> "Horizon3"
        "Repeat founder Ryan Williams launches new fund" -> "Ryan Williams"
    """
    cleaned = title.strip()
    cleaned = re.sub(r"^\[[^\]]+\]\s*", "", cleaned)
    m = re.match(
        r"^(?P<name>[A-Z][A-Za-z0-9.&'-]{1,40}?)\s+(?:raises|raised|secures|secured|closes|closed|nabs|nabbed|lands|landed|hauls|hauled|bags|bagged|scores|scored|extends|extended|announces|announced|hits|gets|raises-on)\b",
        cleaned,
        re.IGNORECASE,
    )
    if m:
        return _clean_name(m.group("name"))
    m = re.match(
        r"^(?P<name>[A-Z][A-Za-z0-9.&'-]{1,40}?),\s+(?:the\s+)?(?:[a-z]|AI\b|raises|closes|secures)",
        cleaned,
    )
    if m:
        return _clean_name(m.group("name"))
    first_words = " ".join(cleaned.split()[:3]).rstrip(",.")
    return _clean_name(first_words)


def _clean_name(raw: str) -> str:
    name = raw.strip().rstrip(",.;:")
    name = re.sub(r"\s+", " ", name).strip()
    return name[:40]


def parse_founded_year(text: str) -> str:
    m = re.search(r"\b(founded|launched|started)\s+in\s+(\d{4})\b", text, re.IGNORECASE)
    if m:
        return m.group(2)
    return ""


def career_page(url: str) -> str:
    if not url:
        return ""
    try:
        host = url.split("/")[2] if "://" in url else url.split("/")[0]
    except IndexError:
        return ""
    if host.startswith("www."):
        host = host[4:]
    if not host.endswith(".com"):
        return ""
    return f"{host}/careers"


def extract_from_tavily(tavily_result: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a single Tavily result into a seed-shaped company dict.

    Pure deterministic parser — no LLM. Uses:
      - ``title`` for company name + funding amount + funding round
      - ``content`` snippet for tagline / headquarters / industry
      - ``published_date`` for the discovery timestamp (raw RFC-2822)
      - ``url`` for the careers-page heuristic

    Output schema matches ``_normalize_company_shape`` exactly so the
    orchestrator and downstream consumers don't care which path
    produced the record.
    """
    title = (tavily_result.get("title") or "").strip()
    content = (tavily_result.get("content") or "").strip()
    raw_content = tavily_result.get("raw_content") or ""
    url = tavily_result.get("url") or ""

    blob = f"{title}\n{content}\n{raw_content}"

    name = extract_name_from_title(title)
    funding_amount = parse_funding_amount(blob)
    funding_round = parse_funding_round(blob)
    headquarters = parse_headquarters(content)
    industry = classify_industry(blob)
    founded = parse_founded_year(blob)
    careers = career_page(url)

    tagline = content.split(". ", 1)[0].strip()
    if len(tagline) > 140:
        tagline = tagline[:137].rstrip() + "..."
    tagline = tagline.replace("\n", " ").replace("#", "").strip()
    if not tagline:
        tagline = f"{name} recently announced a funding round."

    why_hot = title
    if name and why_hot.startswith(name):
        why_hot = why_hot[len(name):].lstrip(" ,.-:")
    why_hot = why_hot.strip()
    if not why_hot:
        why_hot = "Funding news surfaced in last week's cycle."

    return {
        "name": name,
        "tagline": tagline,
        "industry": industry,
        "headquarters": headquarters,
        "funding_round": funding_round,
        "funding_amount": funding_amount,
        "founded": founded,
        "career_page": careers,
        "website": url,
        "why_hot": why_hot,
        "skills": [],
    }


def filter_by_window(
    items: List[Dict[str, Any]],
    window_start: str,
    window_end: str,
) -> List[Dict[str, Any]]:
    """Keep only Tavily results whose ``published_date`` falls inside
    ``[window_start, window_end]``.

    Tavily returns ``published_date`` in RFC-2822 format. If parsing
    fails we err on the side of INCLUSION.
    """
    try:
        ws = datetime.fromisoformat(window_start).replace(tzinfo=timezone.utc)
        we = datetime.fromisoformat(window_end).replace(tzinfo=timezone.utc).replace(
            hour=23, minute=59, second=59
        )
    except ValueError:
        return items

    kept: List[Dict[str, Any]] = []
    for it in items:
        raw_date = (it.get("published_date") or "").strip()
        if not raw_date:
            kept.append(it)
            continue
        try:
            dt = parsedate_to_datetime(raw_date)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            kept.append(it)
            continue
        if ws <= dt <= we:
            kept.append(it)
    return kept


def is_company_funding_article(title: str, content: str) -> bool:
    """Filter out articles that are NOT about a single company raising
    a round. Catches:
      - VC fund announcements (e.g. "Index Ventures raises $2B")
      - Opinion/analysis pieces
      - Conference coverage
      - Q&A / interview articles
      - Articles whose primary subject is NOT a company
    """
    blob = f"{title}\n{content}".lower()

    # The strongest positive signal is "Company X raises / closes / hits
    # $Y Series Z". If present, we trust it.
    funding_verbs = (
        r"\b(raises|raised|secures|secured|closes|closed|nabs|nabbed|"
        r"lands|landed|hauls|hauled|bags|bagged|scores|scored|"
        r"extends|extended|announces|announced|hits)\b"
    )
    if re.search(funding_verbs, blob):
        return True

    # Secondary signal: dollar amount + a funding-round keyword.
    if re.search(r"\$\s*\d", blob) and re.search(
        r"\b(seed|pre[-\s]?seed|series\s+[a-f]|bridge|ipo|valuation)\b",
        blob,
        re.IGNORECASE,
    ):
        return True

    return False


def normalize_window(
    tavily_results: List[Dict[str, Any]],
    window_start: str,
    window_end: str,
) -> List[Dict[str, Any]]:
    """Pure-deterministic pipeline that produces seed-shape records
    WITHOUT calling the LLM.

    Used as the primary path by the Weekly Funding Agent. The LLM
    enrichment layer, if available, refines field values after this.
    """
    filtered = filter_by_window(tavily_results, window_start, window_end)
    filtered = [
        r for r in filtered
        if is_company_funding_article(
            r.get("title", "") or "",
            r.get("content", "") or "",
        )
    ]
    records = [extract_from_tavily(r) for r in filtered]
    records = [r for r in records if r.get("name")]
    seen = set()
    deduped: List[Dict[str, Any]] = []
    for r in records:
        key = r["name"].lower().strip()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    return deduped
