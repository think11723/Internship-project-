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
    """Backward-compatible thin wrapper around the multi-stage pipeline.

    Returns just the company name (or empty string if none could be
    extracted). Prefer ``extract_company_deterministic`` when you need
    the confidence / reason / source metadata.
    """
    extraction = extract_company_deterministic(title=title)
    return extraction["company_name"] or ""


# ---------------------------------------------------------------------------
# Sprint 2: Multi-stage deterministic company extraction.
#
# Replaces the single-regex ``extract_name_from_title`` which greedily
# captured phrases like "Repeat founder Ryan Williams" instead of the
# actual funded company. Four stages run in priority order; each
# returns ``(name, confidence, reason)``. The first stage with the
# highest confidence wins; cross-signal agreement between stages
# boosts confidence and surfaces multiple-source provenance.
# ---------------------------------------------------------------------------

# Headline structures that NEVER carry a company name. Pre-screen
# before the regex runs to avoid guessing on patterns like "Repeat
# founder X raises..." where the actual company is unnamed in the
# headline.
NON_COMPANY_HEADLINE_PATTERNS = [
    r"^Repeat founder\b",
    r"^Serial founder\b",
    r"^Founder\b",
    r"^Co-?founder\b",
    r"^An? \d+-year-old\b",
    r"^An? \w+-year-old\b",
    r"^The (AI|ML|startup|founder|VC|fund)\b",
    r"^(AI|ML|Startup|Bootstrapped)\b",
    r"^(TechCrunch|Crunchbase|VentureBeat|Forbes|WSJ|Reuters|Bloomberg|BusinessWire|PR Newswire)\b",
    r"^Fresh off\b",
    r"^Just\b",
    r"^Why\b",
    r"^What\b",
    r"^How\b",
    r"^When\b",
    r"^Here\b",
    r"^Meet\b",
    r"^This\b",
    r"^That\b",
    r"^Inside\b",
    r"^A look\b",
    r"^Q&A\b",
]

# Funding verbs that anchor a real funding-event headline.
_FUNDING_VERBS = (
    r"(?:raises?|raised|secures?|secured|closes?|closed|nabs?|nabbed|"
    r"lands?|landed|hauls?|hauled|bags?|bagged|scores?|scored|"
    r"extends?|extended|announces?|announced|hits?|gets?|launches?|launched)"
)

# Strict name pattern: a leading uppercase letter followed by 0-40
# alphanumeric/&./'/- characters, then optionally up to 4 MORE
# uppercase-led words. Each word in the run MUST start uppercase —
# this is the structural fix for "Repeat founder Ryan Williams"
# where "founder" is lowercase and breaks the run.
_STRICT_NAME_RUN = (
    r"[A-Z][A-Za-z0-9&.'\-]{0,40}"
    r"(?:\s+[A-Z][A-Za-z0-9&.'\-]{0,40}){0,4}"
)

# URL slug stop-words: words after which the company name does not
# continue in the URL slug. Includes funding verbs and common
# determiners / prepositions / news-narrative words.
_URL_SLUG_STOP_WORDS = {
    "raises", "raised", "secures", "secured", "closes", "closed",
    "nabs", "nabbed", "lands", "landed", "hauls", "hauled",
    "bags", "bagged", "scores", "scored", "extends", "extended",
    "announces", "announced", "hits", "launches", "launched",
    "starts", "started", "plans", "to", "for", "with", "and",
    "the", "a", "an", "is", "its", "his", "her", "their",
    "new", "first", "second", "third", "his", "her", "their",
    "in", "on", "at", "by", "of", "from", "as",
    "raiseson", "raises-up", "raises-up-to",
}

# Words that should never appear as a captured company name token.
# NB: "ai", "ml", "api" etc. are NOT here — they are valid suffixes
# for compound company names ("Mistral AI", "Together AI"). The
# standalone-name check in ``_is_valid_company_name`` rejects those
# when the WHOLE name is just an acronym.
_BLOCKED_NAME_WORDS = {
    "a", "an", "the", "this", "that", "these", "those", "i", "we", "they",
    "techcrunch", "crunchbase", "venturebeat", "forbes", "wsj", "reuters",
    "bloomberg", "businesswire", "prnewswire",
    "repeat", "serial", "founder", "co-founder", "cofounder",
    "ex", "former", "first", "second", "third",
    "just", "now", "today", "yesterday", "tomorrow", "week",
    "fresh", "off", "out", "up", "down", "into", "over",
    "startup", "company", "business", "firm", "team", "group",
    "raises", "raised", "secures", "secured", "closes", "closed",
    "nabs", "nabbed", "lands", "landed", "hauls", "hauled",
    "bags", "bagged", "scores", "scored", "extends", "extended",
    "announces", "announced", "hits", "launches", "launched",
    "report", "reports", "according", "sources", "people",
    "is", "are", "was", "were", "be", "been", "being",
    "build", "make", "making", "meet", "show",
}

# Whole-name blocklist: rejects names that are ONLY these generic
# tokens. Applied in addition to the per-token check.
_BLOCKED_ENTIRE_NAMES = {
    "ai", "ml", "api", "saas", "web3", "ui", "ux",
    "vr", "ar", "iot", "saas", "b2b", "b2c", "mlops",
    "startup", "company", "business", "firm",
}

# Common acronyms that should be fully uppercased when they appear
# as a token (so "ai" -> "AI", not "Ai").
_ACRONYMS = {"ai", "ml", "api", "ui", "ux", "vr", "ar", "iot", "nlp",
             "saas", "b2b", "b2c", "mlops", "devops", "qa", "ux",
             "rl", "rag", "llm", "llms", "gpt"}


def _clean_name(raw: str) -> str:
    """Normalise a captured name: strip trailing punctuation, collapse
    whitespace, truncate. Conservative 50-char limit (was 40) to
    accommodate legitimate names like "Weights & Biases"."""
    name = raw.strip().rstrip(",.;:")
    name = re.sub(r"\s+", " ", name).strip()
    return name[:50]


def _normalize(name: str) -> str:
    """Normalise for cross-signal comparison (lowercase, strip
    punctuation and whitespace)."""
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def _is_valid_company_name(name: str) -> bool:
    """Reject names that are obviously not companies: too short, only
    punctuation, blocked words, single uppercase letter, lowercase
    only, etc. Conservative — returns False rather than guess when
    uncertain."""
    if not name:
        return False
    stripped = name.strip()
    if len(stripped) < 2:
        return False
    # Must contain at least one ASCII letter
    if not re.search(r"[A-Za-z]", stripped):
        return False
    # Must contain at least one uppercase letter (legitimate companies
    # are Capitalised)
    if not re.search(r"[A-Z]", stripped):
        return False
    # Reject single uppercase-letter "names" (A, I, etc.)
    if len(stripped) == 1:
        return False
    # Reject names that are ENTIRELY a generic token ("AI", "ML", etc.)
    whole_lower = stripped.lower().rstrip(".,;:")
    if whole_lower in _BLOCKED_ENTIRE_NAMES:
        return False
    # Reject if any whitespace-separated token is a blocked word
    for token in re.split(r"\s+", stripped):
        if token.lower().rstrip(".,;:") in _BLOCKED_NAME_WORDS:
            return False
    # Reject overly long names (likely sentence fragments)
    if len(stripped) > 50:
        return False
    # Reject names that contain a verb as the leading word (a fragment
    # that begins mid-sentence)
    leading = stripped.split()[0].lower().rstrip(".,;:")
    if leading in _BLOCKED_NAME_WORDS:
        return False
    return True


def _strip_brackets_and_pipes(text: str) -> str:
    """Remove bracketed prefixes like '[Exclusive]' that some outlets
    prepend to headlines."""
    return re.sub(r"^\[[^\]]+\]\s*", "", text or "").strip()


def extract_company_from_headline(
    headline: str,
) -> "tuple[Optional[str], float, str]":
    """Extract company name from a TechCrunch-style headline.

    Returns ``(name, confidence, reason)``. ``name`` is ``None`` if
    the headline does not contain a parseable company name (e.g.
    "Repeat founder X raises...", "Build in public...", "A 25-year-
    old AI...").
    """
    if not headline:
        return (None, 0.0, "empty headline")

    cleaned = _strip_brackets_and_pipes(headline)

    # Pre-screen: reject headline structures that never carry a
    # company name (founders, journalists, publications, fragments).
    for pattern in NON_COMPANY_HEADLINE_PATTERNS:
        if re.search(pattern, cleaned, re.IGNORECASE):
            return (
                None,
                0.0,
                f"headline matches non-company pattern: {pattern}",
            )

    # Strict regex: consecutive capitalised words followed by a
    # funding verb. Lowercase words inside the run break the match.
    strict_pattern = (
        r"^(?P<name>" + _STRICT_NAME_RUN + r")\s+"
        + _FUNDING_VERBS + r"\b"
    )
    m = re.match(strict_pattern, cleaned, re.IGNORECASE)
    if m:
        candidate = _clean_name(m.group("name"))
        if _is_valid_company_name(candidate):
            return (
                candidate,
                0.90,
                "headline: capitalised words before funding verb",
            )
        return (
            None,
            0.0,
            "headline regex matched but candidate failed validation",
        )

    # Pattern: "CompanyName, [verb]..." (e.g. "Anysphere, the maker
    # of Cursor, raises..."). Strict capitalised run before a comma.
    comma_pattern = (
        r"^(?P<name>" + _STRICT_NAME_RUN + r"),\s+"
        + r"(?:the\s+)?(?:[a-z]|AI\b|raises|closes|secures|lands|hits|announces|nabs|scores)"
    )
    m = re.match(comma_pattern, cleaned, re.IGNORECASE)
    if m:
        candidate = _clean_name(m.group("name"))
        if _is_valid_company_name(candidate):
            return (
                candidate,
                0.85,
                "headline: capitalised words before comma+verb",
            )

    # Fallback: "Company announces funding" without a verb-anchored
    # match. Try a comma-anchored strict run.
    m = re.match(r"^(?P<name>" + _STRICT_NAME_RUN + r"),", cleaned)
    if m:
        candidate = _clean_name(m.group("name"))
        if _is_valid_company_name(candidate):
            return (
                candidate,
                0.70,
                "headline: capitalised words before comma",
            )

    return (None, 0.0, "headline: no matching company-name structure")


def extract_company_from_snippet(
    snippet: str,
) -> "tuple[Optional[str], float, str]":
    """Extract company name from the article snippet / first sentence.

    TechCrunch-style snippets typically begin with:
        "Dili, a startup that uses AI to automate compliance..."
        "Anysphere, the maker of Cursor, raised..."

    Anchored regex: capitalised run before a comma.
    """
    if not snippet:
        return (None, 0.0, "empty snippet")

    cleaned = snippet.strip()

    # Anchored: "X, a/an/the/is..."
    m = re.match(
        r"^(?P<name>" + _STRICT_NAME_RUN + r"),\s+"
        + r"(?:a|an|the|is|was|has|—|-)",
        cleaned,
        re.IGNORECASE,
    )
    if m:
        candidate = _clean_name(m.group("name"))
        if _is_valid_company_name(candidate):
            return (
                candidate,
                0.75,
                "snippet: capitalised words before comma+descriptor",
            )

    # Anchored: "X, the [company] that..."  (nested clause)
    m = re.match(
        r"^(?P<name>" + _STRICT_NAME_RUN + r"),\s+",
        cleaned,
    )
    if m:
        candidate = _clean_name(m.group("name"))
        if _is_valid_company_name(candidate):
            return (
                candidate,
                0.65,
                "snippet: capitalised words before comma",
            )

    # Fallback: first capitalised run (no anchor)
    m = re.match(r"^(?P<name>" + _STRICT_NAME_RUN + r")", cleaned)
    if m:
        candidate = _clean_name(m.group("name"))
        if _is_valid_company_name(candidate):
            return (
                candidate,
                0.50,
                "snippet: first capitalised words (no anchor)",
            )

    return (None, 0.0, "snippet: no usable company-name structure")


def extract_company_from_content(
    content: str,
) -> "tuple[Optional[str], float, str]":
    """Extract company name from full article content (Firecrawl
    markdown). Looks for the funding sentence — capitalised run
    before a past-tense funding verb, in a sentence that also
    mentions a dollar amount.
    """
    if not content:
        return (None, 0.0, "empty content")

    # Split into sentences by ". " (best-effort)
    sentences = re.split(r"(?<=[.!?])\s+", content)
    for sent in sentences:
        if "$" not in sent:
            continue
        m = re.search(
            r"\b(?P<name>" + _STRICT_NAME_RUN + r")\s+"
            + r"(?:raised|raises|secured|secures|closed|closes|landed|lands)\b",
            sent,
            re.IGNORECASE,
        )
        if m:
            candidate = _clean_name(m.group("name"))
            if _is_valid_company_name(candidate):
                return (
                    candidate,
                    0.85,
                    "content: funding sentence with $ amount",
                )

    return (None, 0.0, "content: no funding sentence found")


def extract_company_from_url_slug(
    url: str,
) -> "tuple[Optional[str], float, str]":
    """Extract a company-name hint from the URL path slug.

    Most TechCrunch / Crunchbase / Forbes URLs embed the company name
    in the slug:
        techcrunch.com/2026/07/30/dili-raises-15-million-to-...
                          ^ company words until first stop-word
                          -> "dili" -> "Dili"

    Acronym tokens (AI, ML, API, UI, UX, etc.) are uppercased so
    "encore-ai-raises-..." becomes "Encore AI" (not "Encore Ai").
    """
    if not url:
        return (None, 0.0, "empty url")

    path = url.split("?")[0].rstrip("/")
    parts = path.split("/")
    if len(parts) < 1:
        return (None, 0.0, "url: no path")

    slug = parts[-1]
    slug_words = slug.split("-")
    if not slug_words or slug_words == [""]:
        return (None, 0.0, "url: empty slug")

    # Take leading words until a stop-word is hit. Maximum 4 words.
    company_words: list[str] = []
    for w in slug_words:
        if w.lower() in _URL_SLUG_STOP_WORDS:
            break
        # Drop pure numeric / pure punctuation tokens
        if not re.search(r"[A-Za-z]", w):
            continue
        # Acronym-aware capitalisation
        if w.lower() in _ACRONYMS:
            company_words.append(w.upper())
        else:
            company_words.append(w.capitalize())
        if len(company_words) >= 4:
            break

    if not company_words:
        return (None, 0.0, "url: slug has no usable words")

    candidate = _clean_name(" ".join(company_words))
    if not _is_valid_company_name(candidate):
        return (None, 0.0, "url: candidate failed validation")

    return (candidate, 0.55, "url: slug-derived hint")


# Headlines that are NOT funding events: acquisitions, mergers,
# shutdowns, opinion pieces, Q&As. If a headline matches one of these
# the orchestrator returns None, regardless of what other signals say.
_NON_FUNDING_HEADLINE_PATTERNS = [
    r"\bacquired\b",
    r"\bacquisition\b",
    r"\bmerger\b",
    r"\bmerged\b",
    r"\bshuts? down\b",
    r"\bshutdown\b",
    r"\bwind(s|ing)? down\b",
    r"\bcloses down\b",
    r"\bimplodes?\b",
    r"\bpartnership\b",
    r"\bpartners with\b",
    r"\bhelping\b",
    r"\bimplode",
    r"\bdata:",
    r"\bhow\b",
    r"\bwhy\b",
    r"\bwhat\b",
    r"\binterview\b",
    r"\bq&a\b",
    r"\bopinion\b",
    r"\beditorial\b",
    r"\b(op|ed):",
]


def extract_company_deterministic(
    headline: str = "",
    snippet: str = "",
    content: str = "",
    url: str = "",
) -> Dict[str, Any]:
    """Multi-stage deterministic company extractor (no LLM).

    Runs each available signal (headline, snippet, content, URL slug),
    collects candidates with their confidence, and returns the best.
    Cross-signal agreement boosts confidence and surfaces multi-source
    provenance.

    Returns:
        {
            "company_name": str | None,
            "confidence": float,    # 0.00–0.99
            "reason": str,          # human-readable explanation
            "source": str | None,   # "headline", "snippet", "content",
                                    # "url_slug", or "+"-joined combination
        }

    Bad data is worse than missing data. If no stage finds a valid
    company name, ``company_name`` is ``None`` and confidence is 0.0.
    """
    # Non-funding pre-screen: if the headline signals an acquisition,
    # merger, shutdown, opinion piece, or partnership announcement,
    # this is not a single-startup funding event. Return null
    # regardless of other signals. This prevents URL-slug fallback from
    # fabricating a name when the article is about something else.
    if headline:
        for pattern in _NON_FUNDING_HEADLINE_PATTERNS:
            if re.search(pattern, headline, re.IGNORECASE):
                return {
                    "company_name": None,
                    "confidence": 0.0,
                    "reason": (
                        f"headline matches non-funding pattern: {pattern}"
                    ),
                    "source": None,
                }

    candidates: list[tuple[str, float, str, str]] = []

    if headline:
        n, c, r = extract_company_from_headline(headline)
        if n is not None:
            candidates.append((n, c, r, "headline"))

    if snippet:
        n, c, r = extract_company_from_snippet(snippet)
        if n is not None:
            # Snippet follow-up check: if the comma-anchored name is
            # immediately followed by a "founder / co-founder"
            # descriptor, the subject is a PERSON not a company.
            if not _is_founder_descriptor(snippet):
                candidates.append((n, c, r, "snippet"))
            else:
                pass  # silently drop; reason stays from later stages

    if content:
        n, c, r = extract_company_from_content(content)
        if n is not None:
            candidates.append((n, c, r, "content"))

    if url:
        n, c, r = extract_company_from_url_slug(url)
        if n is not None:
            candidates.append((n, c, r, "url_slug"))

    if not candidates:
        return {
            "company_name": None,
            "confidence": 0.0,
            "reason": "no valid company name found in any signal",
            "source": None,
        }

    # Sort by confidence descending; tie-break by source priority.
    source_priority = {"headline": 0, "content": 1, "snippet": 2, "url_slug": 3}
    candidates.sort(
        key=lambda x: (-x[1], source_priority.get(x[3], 99))
    )
    best_name, best_conf, best_reason, best_source = candidates[0]

    # Cross-signal agreement: if 2+ signals normalise to the same
    # name, boost confidence by +0.10 (capped at 0.99) and combine
    # sources into the provenance string.
    agreeing = [
        c for c in candidates
        if _normalize(c[0]) == _normalize(best_name)
    ]
    if len(agreeing) >= 2:
        boosted_conf = min(0.99, best_conf + 0.10)
        sources = sorted({c[3] for c in agreeing})
        reason = best_reason + (
            f"; confirmed by {len(agreeing) - 1} additional signal(s)"
        )
        return {
            "company_name": best_name,
            "confidence": round(boosted_conf, 2),
            "reason": reason,
            "source": "+".join(sources),
        }

    return {
        "company_name": best_name,
        "confidence": round(best_conf, 2),
        "reason": best_reason,
        "source": best_source,
    }


def _is_founder_descriptor(snippet: str) -> bool:
    """Detect if a snippet's leading entity is a PERSON described as
    a founder, not a COMPANY. Patterns matched:
        "Name, a founder"            (1 prefix word)
        "Name, the co-founder"       (1 prefix word)
        "Name, serial founder"       (1 prefix word)
        "Name, a repeat founder"     (2 prefix words)
        "Name, the serial founder"   (2 prefix words)
    """
    if not snippet:
        return False
    head = snippet[:200]  # only first ~200 chars
    return bool(
        re.search(
            r",\s+(?:(?:a|an|the)\s+)?(?:(?:serial|repeat)\s+)?"
            r"(?:co-?founder|founder)\b",
            head,
            re.IGNORECASE,
        )
    )


def parse_founded_year(text: str) -> str:
    m = re.search(r"\b(founded|launched|started)\s+in\s+(\d{4})\b", text, re.IGNORECASE)
    if m:
        return m.group(2)
    return ""


# Sprint 3: domains that NEVER count as company websites. These are
# publishers, aggregators, social platforms, and profile directories.
# The deterministic career-page heuristic returns "" for any of these
# so the article URL never masquerades as the company's site.
_NON_COMPANY_HOSTS = frozenset({
    # News publishers
    "techcrunch.com", "crunchbase.com", "venturebeat.com", "forbes.com",
    "techstartups.com", "reuters.com", "bloomberg.com", "wsj.com",
    "nytimes.com", "tech.co", "yahoo.com", "cnbc.com", "bbc.com",
    "theverge.com", "wired.com", "businessinsider.com", "fastcompany.com",
    "inc.com", "eu-startups.com", "seedtable.com", "sifted.eu",
    "businesswire.com", "prnewswire.com", "globenewswire.com",
    "prweb.com", "einnewswire.com",
    # Aggregators / directories / data providers
    "linkedin.com", "twitter.com", "x.com", "facebook.com", "reddit.com",
    "instagram.com", "youtube.com", "tiktok.com", "medium.com",
    "substack.com", "wikipedia.org", "en.wikipedia.org",
    "crunchbase.com", "pitchbook.com", "cbinsights.com",
    "owler.com", "tracxn.com", "dealroom.co", "f6s.com",
    "wellfound.com", "angel.co", "ycombinator.com",
    "github.com", "gitlab.com", "bitbucket.org",
    "sec.gov", "edgar.sec.gov",
    # Other platforms that are not a company website
    "producthunt.com", "hackernews.com", "news.ycombinator.com",
    "glassdoor.com", "indeed.com", "monster.com",
    "twitter.com", "facebook.com",
})


def career_page(url: str) -> str:
    """Return a best-guess careers URL from the article host, ONLY if
    the host is a plausible company domain (not a publisher/aggregator).

    Sprint 3 change: previously this function blindly returned
    ``f"{host}/careers"`` for any .com host, which produced fake URLs
    like ``techcrunch.com/careers``. Now returns "" for any host in
    ``_NON_COMPANY_HOSTS`` and for hosts without a recognised TLD.

    Common blog subdomains (``blog.``, ``www.``, ``m.``, ``press.``,
    ``about.``, ``cdn.``, ``news.``) are stripped before guess so
    ``blog.anthropic.com`` becomes ``anthropic.com`` (more likely
    to be the canonical careers host).
    """
    if not url:
        return ""
    try:
        host = url.split("/")[2] if "://" in url else url.split("/")[0]
    except IndexError:
        return ""
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]

    # Reject publisher / aggregator hosts.
    if host in _NON_COMPANY_HOSTS:
        return ""

    # Strip common blog subdomains. If host is "blog.anthropic.com"
    # this becomes "anthropic.com".
    for prefix in ("blog.", "press.", "about.", "m.", "cdn.", "news."):
        if host.startswith(prefix):
            host = host[len(prefix):]
            break
    # Also strip www. (after the blog-prefix strip so "blog.www.x.com"
    # doesn't leave a leading "www.").
    if host.startswith("www."):
        host = host[4:]

    # Reject any host ending in a known non-company TLD suffix.
    if not (
        host.endswith(".com")
        or host.endswith(".ai")
        or host.endswith(".io")
        or host.endswith(".co")
        or host.endswith(".app")
        or host.endswith(".dev")
        or host.endswith(".sh")
        or host.endswith(".so")
        or host.endswith(".tech")
        or host.endswith(".xyz")
    ):
        return ""
    return f"https://{host}/careers"


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

    extraction = extract_company_deterministic(
        headline=title,
        snippet=content,
        content=raw_content,
        url=url,
    )
    name = extraction["company_name"]
    extraction_confidence = extraction["confidence"]
    extraction_reason = extraction["reason"]
    extraction_source = extraction["source"]
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
        if name:
            why_hot = "Funding news surfaced in last week's cycle."
        else:
            why_hot = (
                "Article discovered but no company name could be "
                "extracted from the headline."
            )

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
        # Sprint 2: deterministic extraction provenance.
        "extraction_confidence": extraction_confidence,
        "extraction_reason": extraction_reason,
        "extraction_source": extraction_source,
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
