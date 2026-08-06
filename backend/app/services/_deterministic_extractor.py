"""Deterministic extraction helpers for the Weekly Funding Agent.

Pure regex + heuristic parsing. No LLM. Reads Tavily's structured
response (title, url, content, published_date) and emits records in
the same shape as ``discovery_service._normalize_company_shape``.

Sprint 13.7 — Production Stabilization:
  - HTML entities are decoded at every text boundary
    (RSS articles, snippets, article bodies, taglines, why_hot).
  - URL slug extraction rejects Google News tracking IDs and
    article-title slugs (verbs like "makes", "predicts", "transforms").
  - Company-name validation is stricter: rejects single-word
    generic terms ("ai", "startup"), tracking-ID patterns
    (long alphanumeric with no vowels), publisher names.
  - Description cleanup removes trailing URLs, tracking parameters,
    duplicated whitespace, broken unicode, HTML tags/entities.
  - Pre-cache validation rejects records with low confidence or
    unparseable required fields.
"""

import html
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional, Tuple


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
    # Sprint 13.8 — handle "pre-IPO" / "pre IPO" first because the
    # regex below matches the trailing "ipo" as a separate token and
    # would otherwise return "IPO" instead of "Pre-IPO".
    pre_ipo = re.search(r"\bpre[-\s]?ipo\b", text, re.IGNORECASE)
    if pre_ipo:
        return "Pre-IPO"
    m = _FUNDING_ROUND_RE.search(text)
    if not m:
        return ""
    raw = m.group(1).strip().lower()
    # Sprint 13.8 — preserve acronym casing so "ipo" does not
    # become "Ipo".
    if raw == "ipo":
        return "IPO"
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
# continue in the URL slug. Includes funding verbs, common action
# verbs (Sprint 13.7 — prevents article-title slugs like
# "ai-makes-weather-prediction" from being captured as a company
# name), determiners / prepositions / news-narrative words.
_URL_SLUG_STOP_WORDS = {
    "raises", "raised", "secures", "secured", "closes", "closed",
    "nabs", "nabbed", "lands", "landed", "hauls", "hauled",
    "bags", "bagged", "scores", "scored", "extends", "extended",
    "announces", "announced", "hits", "launches", "launched",
    "starts", "started", "plans",
    # Sprint 13.7: action verbs that signal article-title slugs
    # rather than company slugs. When the slug contains any of
    # these, the URL is about an action/event, not a company name.
    "makes", "made", "predicts", "predicted", "creates", "created",
    "helps", "helped", "lets", "lets", "brings", "brought",
    "transforms", "transformed", "changes", "changed", "changing",
    "builds", "built", "uses", "used", "wants", "wanted",
    "reveals", "revealed", "shows", "showed", "tells", "told",
    "thinks", "thought", "believes", "believed", "says", "said",
    "offers", "offered", "provides", "provided", "delivers",
    "delivered", "reaches", "reached", "backs", "backed",
    "acquires", "acquired", "buys", "bought", "sells", "sold",
    "merges", "merged", "shuts", "shut", "dies", "died",
    # Sprint 13.7: ownership / demographic descriptors that
    # signal editorial framing, not company identity
    "owned", "led", "run", "founded", "headquartered",
    # Sprint 13.7: prepositions, determiners, news-narrative
    "to", "for", "with", "and", "the", "a", "an",
    "is", "its", "his", "her", "their",
    "new", "first", "second", "third", "this", "that",
    "in", "on", "at", "by", "of", "from", "as",
    "after", "before", "during", "while", "because",
    "raiseson", "raises-up", "raises-up-to",
    # Sprint 13.7: geographic / temporal qualifiers that
    # frequently appear in editorial article slugs
    "today", "yesterday", "tomorrow", "week", "month", "year",
    "former", "ex",
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
    # Sprint 13.8 — common editorial prefix / framing words that
    # surface when an article body begins with "[Exclusive]",
    # "Sponsored:", "Opinion:", etc. After the bracket stripper
    # removes the brackets, these words remain as the first
    # capitalised token. None of them is a company name anywhere
    # in a candidate.
    "exclusive", "sponsored", "opinion", "editorial", "oped",
    "breaking", "update", "alert", "preview", "review",
    "analysis", "explainer", "scoop", "rumor", "rumour",
    "leaked", "unconfirmed", "verified",
}

# Sprint 13.8 — words that are blocked ONLY when they appear as the
# LEADING token of a candidate. They are valid as suffixes (so
# "Mistral AI" / "Together AI" still pass) but never as the first
# word of a real company name (so "Legal AI" / "Enterprise AI" /
# "AI startup" all reject).
_LEADING_BLOCKED_WORDS = {
    "ai", "ml", "api", "genai", "llm", "rag", "saas", "iot",
    "legal", "enterprise", "generative", "predictive",
    "conversational", "agentic", "foundation", "open-source",
    "open", "proprietary", "commercial", "consumer",
    "vertical", "horizontal", "embedded", "edge", "cloud",
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
    only, tracking IDs, etc. Conservative — returns False rather than
    guess when uncertain.

    Sprint 13.7 hardening:
      - Reject names that contain HTML entities (``&amp;``, ``&quot;``).
      - Reject tracking-ID-looking names (long alphanumeric with no
        vowels or no real word root).
      - Reject names that begin with action verbs ("Makes Weather
        Prediction") — these are article-title fragments, not
        companies.
    """
    if not name:
        return False
    stripped = name.strip()
    if len(stripped) < 2:
        return False
    # Sprint 13.7: any HTML entity that survived upstream decoding
    # means the candidate was never a real company name.
    if re.search(r"&[a-z]+;|&#\d+;", stripped, re.IGNORECASE):
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
    # Sprint 13.8 — also reject the LEADING token when it is a
    # category / industry word ("Legal AI", "Enterprise AI",
    # "AI startup"). These are valid as SUFFIX tokens (so "Mistral
    # AI" still passes) but never as the first word of a real
    # company name.
    if leading in _LEADING_BLOCKED_WORDS:
        return False
    # Sprint 13.7: reject tracking-ID-looking names regardless of
    # token-level checks. E.g. "Cbmiuwfbvv95" has all-uppercase letters
    # and no blocked tokens, but is still garbage.
    if _looks_like_tracking_id(stripped):
        return False
    # Sprint 13.7: if the first word is a known article-title action
    # verb, the candidate is a headline fragment, not a company.
    first_word = stripped.split()[0].lower().rstrip(".,;:'-")
    article_action_verbs = {
        "makes", "made", "predicts", "creates", "created",
        "helps", "lets", "brings", "transforms", "changes",
        "builds", "built", "uses", "wants", "reveals",
        "shows", "tells", "thinks", "believes", "says",
        "offers", "provides", "delivers", "reaches",
    }
    if first_word in article_action_verbs:
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

    # Sprint 13.8 — anchored: "X startup/company Y raises/closes..."
    # When the snippet starts with a category phrase like
    # "Legal AI startup NYAI raises $1.5mn...", the FIRST capitalised
    # run is the category ("Legal AI"), not the company ("NYAI").
    # The company name is the capitalised run IMMEDIATELY AFTER the
    # word "startup" / "company" / "firm" / "platform" and BEFORE
    # the funding verb. The positive lookahead ``(?=\s+(?:raises|...))``
    # is critical: it stops the name group from greedily consuming
    # the verb ("raises") under re.IGNORECASE — without it, [A-Z]
    # also matches lowercase and the name group eats "NYAI raises".
    m = re.match(
        r"^(?P<category>" + _STRICT_NAME_RUN + r")\s+"
        r"(?:startup|start-up|company|firm|platform|player|"
        r"vendor|provider)\s+"
        r"(?P<name>" + _STRICT_NAME_RUN + r")"
        r"(?=\s+(?:raises|raised|secures|secured|closes|closed|"
        r"lands|landed|nabs|nabbed|announces|announced|hits|"
        r"scores|scored)\b)",
        cleaned,
        re.IGNORECASE,
    )
    if m:
        candidate = _clean_name(m.group("name"))
        if _is_valid_company_name(candidate):
            return (
                candidate,
                0.70,
                "snippet: capitalised run after category word",
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


def _looks_like_tracking_id(token: str) -> bool:
    """Detect Google News / publisher tracking IDs that survive the
    slug parser. Sprint 13.7.

    Google News URLs look like:
      news.google.com/rss/articles/CBMiXWh0dHBz...
      -> slug token "CBMiXWh0dHBz..."

    Heuristics:
      - Token starts with the CBMi prefix (Google News Base64-encoded
        article ID).
      - Token is longer than 12 characters AND has a high consonant /
        digit ratio (looks like a hash, not a name).
      - Token contains no vowels at all and length > 8 (e.g. "CBMi").

    Sprint 13.8 — when a token has the shape ``letters + trailing
    digits`` (e.g. ``Cbmiuwfbvv95`` or ``Horizon3``), check whether
    the alphabetic prefix is a recognisable English word. Real
    product names like ``Horizon3`` / ``Web3`` / ``GPT4`` have a
    recognisable root word; tracking-ID fragments like
    ``Cbmiuwfbvv95`` / ``CbmiXWh0dHBz`` do not.

    Vowel density heuristic: a real word of length N has roughly
    N/3 to N/2 vowels (i.e. 33-50% vowel ratio). A hash fragment
    has 0-20% vowels. We combine this with the presence of digits
    so the heuristic fires only on token shapes that look like
    alpha-hash hybrids, never on plain product-version suffixes
    that happen to have low vowels (e.g. "Crypt1k" -> still has
    reasonable vowels and is short).
    """
    if not token:
        return True
    # Google News Base64-prefixed tracking IDs
    if re.match(r"^CBMi[A-Za-z0-9]+$", token):
        return True
    # Pure-hash pattern: > 12 chars, mostly alphanumeric, ≤ 1 vowel
    if len(token) > 12:
        vowels = sum(1 for c in token.lower() if c in "aeiouy")
        if vowels <= 1:
            return True
    # Sprint 13.8 — mixed alpha+digit suffix pattern. Only reject
    # when the alphabetic prefix has a LOW vowel ratio AND the
    # total token contains digits. Real product-version suffixes
    # ("Horizon3", "Web3", "GPT4") have reasonable vowel ratios
    # in their prefix and a single trailing digit, while hash
    # fragments ("Cbmiuwfbvv95", "CbmiXWh0dHBz") have 11-12
    # chars in the prefix with very few vowels AND digits mixed
    # throughout (or a 2-digit suffix).
    m = re.match(r"^([A-Za-z]+)(\d*)$", token)
    if m:
        alpha = m.group(1)
        digits = m.group(2)
        # Only consider tokens long enough to be hash-like
        if len(alpha) >= 8 and digits:
            vowels = sum(1 for c in alpha.lower() if c in "aeiouy")
            vowel_ratio = vowels / max(len(alpha), 1)
            # Strict cutoff: < 20% vowels in an 8+ char prefix
            # with ANY digits is hash-shaped. "Cbmiuwfbvv95" has
            # prefix "Cbmiuwfbvv" (10 chars, 2 vowels = 20% — still
            # suspicious because the consonants include the
            # non-word "Cw", "fw", "bv" clusters).
            #
            # Tighten: also flag tokens where the prefix has 2+
            # consecutive consonants anywhere (a sign of a hash
            # rather than a word). "Cbmiuwfbvv" has "fb", "bv".
            # "Horizon" has none.
            if vowel_ratio < 0.20:
                return True
            if vowel_ratio < 0.30 and re.search(
                r"[bcdfghjklmnpqrstvwxyz]{3,}", alpha.lower()
            ):
                return True
    return False


def _is_valid_slug_token(token: str) -> bool:
    """Sprint 13.7: per-token gate before accepting it as part of
    a company name from a URL slug.

    Rejects:
      - Tracking IDs (Google News CBMi* hashes)
      - Pure-numeric tokens (years like "2026", "07", "30")
      - Tokens containing only special characters
      - Tokens longer than 30 chars (likely hashes)
      - Tokens that contain digits AND are > 12 chars (likely hashes)
    """
    if not token:
        return False
    if len(token) > 30:
        return False
    if _looks_like_tracking_id(token):
        return False
    # Pure digits (years like "2026", "07") — not company names
    if token.isdigit():
        return False
    # Must contain at least one letter
    if not re.search(r"[A-Za-z]", token):
        return False
    # Tokens that mix digits into a "word" longer than 12 chars are
    # likely hashes, not company names (e.g. "abc123def456")
    if len(token) > 12 and any(c.isdigit() for c in token):
        return True if False else False  # reject
    return True


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

    Sprint 13.7 hardening:
      - Reject Google News ``/articles/CBMi*...`` tracking IDs.
      - Reject tokens that look like hashes (>12 chars, no vowels,
        mixed alpha/digit).
      - Reject article-title slugs that contain action verbs like
        "makes", "predicts", "transforms" (added to stop words).
    """
    if not url:
        return (None, 0.0, "empty url")

    path = url.split("?")[0].rstrip("/")
    parts = path.split("/")
    if len(parts) < 1:
        return (None, 0.0, "url: no path")

    # Sprint 13.7: explicit Google News / publisher tracking-ID paths.
    # If the URL contains a known tracking pattern, skip slug
    # extraction entirely — there is no company name to extract.
    if any(token in path.lower() for token in (
        "/articles/", "/read/", "/rss/articles/",
    )):
        return (None, 0.0, "url: publisher tracking-ID path")

    slug = parts[-1]
    slug_words = slug.split("-")
    if not slug_words or slug_words == [""]:
        return (None, 0.0, "url: empty slug")

    # Take leading words until a stop-word is hit. Maximum 4 words.
    company_words: list[str] = []
    for w in slug_words:
        if w.lower() in _URL_SLUG_STOP_WORDS:
            break
        # Sprint 13.7: per-token gate before accepting
        if not _is_valid_slug_token(w):
            # Either a tracking id, a year, or pure punctuation —
            # treat as a hard break so we don't keep harvesting
            # words after it.
            break
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

    # Sprint 13.7: a single-word URL slug like "black" or "weather"
    # is almost always an editorial framing word, not a company
    # name. Require >= 2 words OR a minimum 5-letter single word.
    if len(company_words) == 1:
        only = company_words[0].lower()
        if len(only) < 5:
            return (
                None,
                0.0,
                "url: single short slug word (likely editorial)",
            )
        if only in {
            "black", "white", "brown", "asian", "latino",
            "former", "ex", "new", "old", "big", "small",
            "top", "best", "worst", "first", "last",
            "weather", "health", "money", "world",
        }:
            return (
                None,
                0.0,
                f"url: single-word slug is an editorial descriptor: {only!r}",
            )

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
    # Sprint 13.8 — Google News is a news aggregator, never a
    # company website. Without this guard, every Google News
    # article produced "google.com/careers" as the careers URL.
    "google.com", "news.google.com", "google.co.uk",
    "google.co.in", "google.com.au", "google.ca",
    "google.de", "google.fr", "google.co.jp", "google.com.br",
    "google.com.mx", "google.es", "google.it", "google.com.hk",
    # Common generic-content hosts whose TLDs slip through the
    # TLD allow-list but are never company sites.
    "goo.gl", "bit.ly", "tinyurl.com", "ow.ly", "t.co",
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


def _decode_html_entities(text: str) -> str:
    """Sprint 13.7: decode all HTML entities in ``text``.

    Uses ``html.unescape`` (Python stdlib) which handles named
    entities (``&nbsp;`` -> ``" "``, ``&quot;`` -> ``'"'``,
    ``&ldquo;`` -> ``"“"``, ``&rdquo;`` -> ``"”"``,
    ``&amp;`` -> ``'&'``, ``&#39;`` -> ``"'"``) and numeric
    entities (``&#1234;`` -> the corresponding codepoint).

    Also normalises curly quotes to straight quotes so downstream
    JSON encoding never emits ``“`` / ``”`` in payload
    strings, and replaces non-breaking space (U+00A0) with a
    regular ASCII space so the regex-based name extractor doesn't
    choke on the whitespace.
    """
    if not text:
        return ""
    decoded = html.unescape(text)
    # Replace common Unicode whitespace with regular ASCII space.
    # Using chr() codes (rather than literal characters in the
    # source) so the source file itself stays 7-bit ASCII clean.
    for ws in (chr(0x00A0), chr(0x202F), chr(0x2009), chr(0x200A), chr(0xFEFF)):
        decoded = decoded.replace(ws, " ")
    # Normalise curly quotes -> straight ASCII
    decoded = (
        decoded.replace(chr(0x201C), '"')
               .replace(chr(0x201D), '"')
               .replace(chr(0x2018), '\'')
               .replace(chr(0x2019), '\'')
    )
    return decoded


_TRACKING_PARAM_RE = re.compile(
    r"[?&](utm_[a-z_]+|fbclid|gclid|mc_cid|mc_eid|ref|ref_src|source)=[^&\s]*",
    re.IGNORECASE,
)
_TRAILING_URL_RE = re.compile(r"https?://\S+$", re.IGNORECASE)
_INLINE_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_BROKEN_UNICODE_RE = re.compile(r"[\uFFFD\u0000-\u0008\u000B-\u001F]+")
_MULTI_WS_RE = re.compile(r"\s+")


def _clean_description(text: str, max_length: int = 240) -> str:
    """Sprint 13.7: produce a frontend-safe description string.

    Pipeline (in order):
      1. Decode HTML entities.
      2. Remove inline URLs (Trafilatura occasionally leaves them
         in the snippet when an article body has a trailing link).
      3. Remove tracking parameters (utm_*, fbclid, gclid, ref, etc.).
      4. Remove broken Unicode (replacement characters, control
         bytes).
      5. Remove duplicate whitespace.
      6. Trim to ``max_length`` characters, breaking on a word
         boundary so we never emit a half-word.
      7. Strip leading/trailing punctuation artefacts.
    """
    if not text:
        return ""
    text = _decode_html_entities(text)
    # Strip trailing URL fragments common in Trafilatura output
    text = _TRAILING_URL_RE.sub("", text)
    # Strip inline URLs from the body too
    text = _INLINE_URL_RE.sub("", text)
    # Drop tracking parameters that may be embedded in plain text
    text = _TRACKING_PARAM_RE.sub("", text)
    # Drop broken unicode / control bytes
    text = _BROKEN_UNICODE_RE.sub("", text)
    # Collapse whitespace
    text = _MULTI_WS_RE.sub(" ", text).strip()
    # Trim to a readable length, on a word boundary
    if len(text) > max_length:
        truncated = text[:max_length]
        # Try to end on a word boundary
        last_space = truncated.rfind(" ")
        if last_space > max_length * 0.6:
            truncated = truncated[:last_space]
        text = truncated.rstrip(" ,.-;:") + "..."
    # Strip leading/trailing punctuation artefacts
    text = text.strip(" \t\n\r\"'`.,;:!?-")
    return text


def _extract_score(
    title: str,
    content: str,
    extraction_confidence: float,
    has_funding_amount: bool,
    has_funding_round: bool,
    has_headquarters: bool,
    has_industry: bool,
) -> int:
    """Sprint 13.7: produce a 0-100 ``extraction_score`` for the
    record. Combines the per-field extraction confidence with
    completeness signals (funding amount, round, HQ, industry).

    Heuristic weights:
      - Base score = ``extraction_confidence`` * 60  (max 60 pts)
      - +10 if funding amount parsed
      - +10 if funding round parsed
      - +5  if headquarters parsed
      - +10 if industry is non-default (i.e. classified rather than
            falling back to "AI")
      - +5  if the headline / content contains a funding-verb match
            (the canonical "raises / closes / lands $X" pattern)

    Bad data is worse than missing data. The score is conservative:
    a record must clear the threshold (default 50) to be admitted
    to the cache. Anything below is rejected and logged.
    """
    score = int(round(extraction_confidence * 60))
    if has_funding_amount:
        score += 10
    if has_funding_round:
        score += 10
    if has_headquarters:
        score += 5
    if has_industry:
        score += 10
    blob = f"{title}\n{content}".lower()
    if re.search(
        r"\b(raises|raised|secures|secured|closes|closed|nabs|nabbed|"
        r"lands|landed|hauls|hauled|bags|bagged|scores|scored|"
        r"extends|extended|announces|announced|hits)\b",
        blob,
    ):
        score += 5
    return max(0, min(100, score))


_EXTRACTION_SCORE_THRESHOLD = 50


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

    Sprint 13.7 hardening:
      - All text fields are HTML-decoded before parsing.
      - Tagline and why_hot go through ``_clean_description``.
      - ``extraction_score`` (0-100) is attached. Records below the
        threshold (``_EXTRACTION_SCORE_THRESHOLD``) are still emitted
        by this function (callers decide whether to keep them) but
        are flagged with ``below_quality_threshold=True`` so the
        cache writer can drop them.
    """
    raw_title = (tavily_result.get("title") or "").strip()
    raw_content = (tavily_result.get("content") or "").strip()
    raw_body = tavily_result.get("raw_content") or ""
    url = tavily_result.get("url") or ""

    # Sprint 13.7: decode HTML entities at the boundary.
    title = _decode_html_entities(raw_title)
    content = _decode_html_entities(raw_content)
    body = _decode_html_entities(raw_body)
    url = _decode_html_entities(url)

    blob = f"{title}\n{content}\n{body}"

    extraction = extract_company_deterministic(
        headline=title,
        snippet=content,
        content=body,
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

    # Sprint 13.7: tagline is the first sentence of content, cleaned.
    first_sentence = content.split(". ", 1)[0].strip()
    tagline = _clean_description(first_sentence, max_length=160)
    if not tagline:
        if name:
            tagline = f"{name} recently announced a funding round."
        else:
            tagline = ""

    # Sprint 13.7: why_hot is the cleaned headline with the company
    # name prefix stripped, so the user sees the editorial angle
    # without redundant repetition of the name.
    why_hot = _clean_description(title, max_length=240)
    if name and why_hot.lower().startswith(name.lower()):
        # Strip the name prefix (case-insensitive). This is best-
        # effort; if the cleaned headline no longer begins with the
        # name, leave it as-is.
        why_hot = why_hot[len(name):].lstrip(" ,.-:")
        why_hot = _clean_description(why_hot, max_length=240)
    if not why_hot:
        if name:
            why_hot = "Funding news surfaced in last week's cycle."
        else:
            why_hot = ""

    extraction_score = _extract_score(
        title=title,
        content=content,
        extraction_confidence=extraction_confidence,
        has_funding_amount=bool(funding_amount),
        has_funding_round=bool(funding_round),
        has_headquarters=bool(headquarters),
        has_industry=bool(industry and industry != "AI"),
    )
    below_threshold = extraction_score < _EXTRACTION_SCORE_THRESHOLD

    # RC-3 — populate ``skills`` from the available evidence blob.
    # We pass title + content + body + tagline + why_hot + industry as
    # the scan text. Industry is included because it's already
    # derived from the article text by ``classify_industry``.
    skills_text = " ".join(
        [
            title or "",
            content or "",
            body or "",
            tagline or "",
            why_hot or "",
        ]
    )
    skills = extract_skills_from_text(skills_text, industry=industry or "")

    return {
        "name": name,
        "tagline": tagline,
        "industry": industry,
        "headquarters": headquarters,
        "funding_round": funding_round,
        "funding_amount": funding_amount,
        "founded": founded,
        "career_page": careers,
        # Sprint 13.8 — leave ``website`` empty. The RSS article URL
        # is NEVER the company website (it points to a publisher
        # page). The enrichment stage (``company_enricher``) is the
        # only place that should populate this field. Previously we
        # stored the article URL here, which leaked into every
        # downstream consumer and caused the frontend to link to
        # techcrunch.com / google.com for every company.
        "website": "",
        "source_url": url,
        "why_hot": why_hot,
        # RC-3 — deterministic skill extraction populated above.
        "skills": skills,
        # Sprint 2: deterministic extraction provenance.
        "extraction_confidence": extraction_confidence,
        "extraction_reason": extraction_reason,
        "extraction_source": extraction_source,
        # Sprint 13.7: quality scoring + threshold flag.
        "extraction_score": extraction_score,
        "below_quality_threshold": below_threshold,
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

    Sprint 13.7 hardening:
      - Records with ``below_quality_threshold=True`` (extraction
        score < ``_EXTRACTION_SCORE_THRESHOLD``) are dropped here.
      - Records without a parseable company name are dropped.
      - A final post-filter (``is_valid_company_record``) re-checks
        every surviving record's required fields. Bad data is worse
        than missing data.
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
    seen: set = set()
    deduped: List[Dict[str, Any]] = []
    for r in records:
        key = r["name"].lower().strip()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    return deduped


# ---------------------------------------------------------------------------
# Sprint 13.7 — Pre-cache validation gate.
#
# Called by the orchestrator / weekly funding agent BEFORE the cache is
# written. Rejects records whose required fields are missing or whose
# company name fails final structural validation. ``UNKNOWN`` names are
# rejected per the Task 1 instruction ("DO NOT fabricate. Return
# UNKNOWN" — which we treat as "do not cache").
# ---------------------------------------------------------------------------


_REQUIRED_RECORD_FIELDS = ("name", "tagline", "funding_amount",
                          "funding_round", "industry")


def validate_company_record(record: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate a single company record before it is admitted to the
    cache. Returns ``(is_valid, list_of_failure_reasons)``.

    Sprint 13.7 — Production Stabilization — Data Quality.

    Rules:
      - ``name`` must be a non-empty string that passes
        ``_is_valid_company_name``.
      - ``name`` must NOT be ``"UNKNOWN"`` (we never fabricate).
      - ``name`` must NOT contain HTML entities or URL fragments.
      - ``name`` must NOT look like a Google News tracking ID.
      - ``tagline``, ``funding_amount``, ``funding_round``,
        ``industry`` must each be non-empty.
      - ``funding_amount`` must match a recognised format (e.g. "$10M",
        "$2.5B").
      - ``extraction_score`` must be at or above
        ``_EXTRACTION_SCORE_THRESHOLD``.
    """
    failures: List[str] = []
    if not isinstance(record, dict):
        return (False, ["record is not a dict"])

    name = (record.get("name") or "").strip()
    if not name:
        failures.append("missing name")
    elif name.upper() == "UNKNOWN":
        failures.append("name is UNKNOWN (refusing to fabricate)")
    elif not _is_valid_company_name(name):
        failures.append(f"name failed validation: {name!r}")
    elif re.search(r"&[a-z]+;|&#\d+;", name, re.IGNORECASE):
        failures.append(f"name contains HTML entities: {name!r}")
    elif _looks_like_tracking_id(name):
        failures.append(f"name looks like a tracking ID: {name!r}")

    for field in _REQUIRED_RECORD_FIELDS:
        value = record.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            failures.append(f"missing or empty {field}")

    funding_amount = (record.get("funding_amount") or "").strip()
    if funding_amount and not re.match(
        r"^\$\s*\d+(\.\d+)?\s*[KMBmb]?$",
        funding_amount.replace(",", ""),
    ):
        failures.append(f"unparseable funding_amount: {funding_amount!r}")

    score = int(record.get("extraction_score") or 0)
    if score < _EXTRACTION_SCORE_THRESHOLD:
        failures.append(
            f"extraction_score {score} < threshold {_EXTRACTION_SCORE_THRESHOLD}"
        )

    return (not failures, failures)


def filter_records(records: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]],
                                                            List[Dict[str, Any]]]:
    """Apply ``validate_company_record`` to every record in ``records``.

    Returns ``(valid_records, rejected_records_with_reason)``. The
    rejected list mirrors the input list but each entry has an
    extra ``rejection_reasons`` field for downstream logging and
    for the verification script.
    """
    valid: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    for rec in records or []:
        ok, reasons = validate_company_record(rec)
        if ok:
            valid.append(rec)
        else:
            rejected.append({**rec, "rejection_reasons": reasons})
    return valid, rejected


# ---------------------------------------------------------------------------
# RC-3 — Deterministic skill extraction.
#
# The RSS discovery pipeline produced companies with ``skills: []``
# because no extraction step existed for the technology vocabulary that
# actually appears in funding article text. This module fills that gap
# with a curated, fully-deterministic extractor:
#
#   1. A canonical -> [aliases] vocabulary covering the tech + domain
#      terms that realistically appear in startup funding articles.
#   2. A word-boundary scan over the available evidence blob
#      (title + content + body + tagline + why_hot + industry).
#   3. Alias collapsing — e.g. "JavaScript"/"JS"/"Javascript" all
#      resolve to the canonical "JavaScript".
#   4. Capped at 15 skills. Never invents, never reads from funding
#      stage or company name. Industry IS evidence-derived, so it's
#      included in the scan blob.
# ---------------------------------------------------------------------------


# Canonical name -> list of lowercased aliases (the canonical itself is
# included as the first alias). Each alias is matched as a
# word-boundary token against the evidence blob.
_SKILL_VOCAB = {
    # --- AI / ML core ---
    "AI":                ["ai", "a.i.", "artificial intelligence"],
    "Machine Learning":  ["machine learning", "ml"],
    "Deep Learning":     ["deep learning"],
    "Neural Networks":   ["neural network", "neural networks"],
    "NLP":               ["nlp", "natural language processing"],
    "Computer Vision":   ["computer vision", "cv", "vision ai"],
    "Speech Recognition": ["speech recognition", "speech-to-text", "stt", "tts"],
    "LLMs":              ["llm", "llms", "large language model",
                         "large language models", "language model",
                         "language models"],
    "GPT":               ["gpt", "gpt-4", "gpt-5", "chatgpt"],
    "Claude":            ["claude", "anthropic claude"],
    "Generative AI":     ["generative ai", "genai", "gen-ai"],
    "Agents":            ["agent", "agents", "agentic",
                         "multi-agent", "ai agent", "ai agents"],
    "RAG":               ["rag", "retrieval augmented generation",
                         "retrieval-augmented generation"],
    "Embeddings":        ["embedding", "embeddings"],
    "Vector Database":   ["vector database", "vector store", "vector search"],
    "Fine-Tuning":       ["fine-tuning", "finetuning", "fine tune"],
    "Reinforcement Learning": ["reinforcement learning", "rlhf"],
    "Diffusion Models":  ["diffusion", "stable diffusion"],
    "Transformers":      ["transformer", "transformers"],
    # --- AI infra / frameworks ---
    "PyTorch":           ["pytorch"],
    "TensorFlow":        ["tensorflow", "tf"],
    "JAX":               ["jax"],
    "Keras":             ["keras"],
    "scikit-learn":      ["scikit-learn", "sklearn"],
    "Hugging Face":      ["huggingface", "hugging face"],
    "LangChain":         ["langchain"],
    "LlamaIndex":        ["llamaindex", "llama index"],
    "OpenAI":            ["openai"],
    "ONNX":              ["onnx"],
    "PyTorch Lightning": ["pytorch lightning", "lightning ai"],

    # --- Languages ---
    "Python":            ["python"],
    "JavaScript":        ["javascript", "js", "java script"],
    "TypeScript":        ["typescript", "ts"],
    "Go":                ["golang", "go-lang"],
    "Rust":              ["rust"],
    "Java":              ["java"],
    "Kotlin":            ["kotlin"],
    "Swift":             ["swift"],
    "Ruby":              ["ruby"],
    "C++":               ["c++", "cpp"],
    "PHP":               ["php"],
    "Scala":             ["scala"],
    "Elixir":            ["elixir"],

    # --- Web / Frontend ---
    "React":             ["react", "react.js", "reactjs"],
    "Next.js":           ["next.js", "nextjs"],
    "Vue":               ["vue", "vue.js", "vuejs"],
    "Svelte":            ["svelte"],
    "Angular":           ["angular", "angular.js"],
    "Remix":             ["remix"],
    "SvelteKit":         ["sveltekit", "svelte-kit"],
    "Tailwind CSS":      ["tailwind", "tailwindcss", "tailwind css"],
    "HTML":              ["html"],
    "CSS":               ["css"],
    "WebAssembly":       ["webassembly", "wasm"],
    "WebGL":             ["webgl"],

    # --- Backend frameworks ---
    "Node.js":           ["node.js", "nodejs", "node js"],
    "Express":           ["express", "express.js", "expressjs"],
    "NestJS":            ["nestjs", "nest.js"],
    "FastAPI":           ["fastapi", "fast api"],
    "Django":            ["django"],
    "Flask":             ["flask"],
    "Spring Boot":       ["spring boot", "spring-boot"],
    "Rails":             ["rails", "ruby on rails", "ror"],
    "Laravel":           ["laravel"],
    "GraphQL":           ["graphql", "graph ql"],
    "gRPC":              ["grpc"],
    "REST":              ["rest api", "restful", "rest apis"],
    "WebSockets":        ["websocket", "websockets"],

    # --- Mobile ---
    "iOS":               ["ios"],
    "Android":           ["android"],
    "React Native":      ["react native", "react-native"],
    "Flutter":           ["flutter"],
    "SwiftUI":           ["swiftui"],

    # --- Databases ---
    "PostgreSQL":        ["postgresql", "postgres", "pg"],
    "MySQL":             ["mysql"],
    "MongoDB":           ["mongodb", "mongo"],
    "Redis":             ["redis"],
    "Elasticsearch":     ["elasticsearch", "elastic search"],
    "Snowflake":         ["snowflake"],
    "DynamoDB":          ["dynamodb", "dynamo db"],
    "Cassandra":         ["cassandra"],
    "Neo4j":             ["neo4j"],
    "InfluxDB":          ["influxdb"],

    # --- Cloud / DevOps ---
    "AWS":               ["aws", "amazon web services"],
    "Azure":             ["azure", "microsoft azure"],
    "GCP":               ["gcp", "google cloud", "google cloud platform"],
    "Cloudflare":        ["cloudflare"],
    "Vercel":            ["vercel"],
    "Netlify":           ["netlify"],
    "Firebase":          ["firebase"],
    "Supabase":          ["supabase"],
    "Docker":            ["docker"],
    "Kubernetes":        ["kubernetes", "k8s"],
    "Terraform":         ["terraform"],
    "Ansible":           ["ansible"],
    "GitHub Actions":    ["github actions"],
    "CircleCI":          ["circleci", "circle ci"],
    "Jenkins":           ["jenkins"],
    "Prometheus":        ["prometheus"],
    "Grafana":           ["grafana"],
    "Datadog":           ["datadog"],
    "Kafka":             ["kafka"],
    "RabbitMQ":          ["rabbitmq"],
    "NATS":              ["nats"],
    "gRPC":              ["grpc"],
    "WebRTC":            ["webrtc"],

    # --- Data / streaming ---
    "Apache Spark":      ["apache spark", "spark"],
    "Apache Flink":      ["flink"],
    "Apache Kafka":      ["apache kafka"],
    "Apache Airflow":    ["airflow"],
    "dbt":               ["dbt"],
    "Databricks":        ["databricks"],
    "Snowflake":         ["snowflake"],
    "Tableau":           ["tableau"],
    "Looker":            ["looker"],

    # --- Security / Auth ---
    "OAuth":             ["oauth", "oauth2"],
    "JWT":               ["jwt"],
    "Cybersecurity":      ["cybersecurity", "cyber security",
                         "security", "infosec", "application security"],
    "Zero Trust":        ["zero trust"],
    "SOC 2":             ["soc 2", "soc2"],
    "GDPR":              ["gdpr"],
    "HIPAA":             ["hipaa"],
    "PCI DSS":           ["pci dss", "pci-dss"],
    "Encryption":        ["encryption", "end-to-end encryption"],

    # --- Payments / commerce ---
    "Stripe":            ["stripe"],
    "PayPal":            ["paypal"],
    "Plaid":             ["plaid"],

    # --- Dev tools / collaboration ---
    "Git":               ["git"],
    "GitHub":            ["github"],
    "GitLab":            ["gitlab"],
    "Figma":             ["figma"],
    "Notion":            ["notion"],
    "Linear":            ["linear"],

    # --- Domain verticals ---
    "LegalTech":         ["legaltech", "legal tech", "legal ai"],
    "FinTech":           ["fintech", "fin tech", "financial technology"],
    "HealthTech":        ["healthtech", "health tech", "digital health"],
    "EdTech":            ["edtech", "education technology"],
    "AdTech":            ["adtech", "ad tech"],
    "PropTech":          ["proptech", "prop tech"],
    "SalesTech":         ["salestech", "sales tech", "sales automation",
                         "sales platform"],
    "Climate Tech":      ["climate tech", "climate-tech", "cleantech",
                         "clean tech"],
    "Weather Forecasting": ["weather forecasting", "weather forecast",
                            "weather prediction", "weather forecasts"],
    "Robotics":          ["robotics", "robots", "robotic"],
    "IoT":               ["iot", "internet of things"],
    "Blockchain":        ["blockchain", "distributed ledger"],
    "Web3":              ["web3"],
    "Quantum Computing": ["quantum computing", "quantum"],

    # --- Infrastructure / domain terms more likely in headlines ---
    "Edge Computing":    ["edge computing", "edge compute", "edge ai"],
    "Voice":             ["voice ai", "voice tech", "voice technology",
                         "voice assistant"],
    "Video":             ["video ai", "video generation", "video model"],
    "Image Generation":  ["image generation", "image gen", "text-to-image"],
    "3D":                ["3d generation", "3d modeling", "3d model"],
    "Predictive Analytics": ["predictive analytics", "forecasting",
                              "predictive"],
    "Voice Agents":      ["voice agents", "voice agent", "voice assistant"],
    "Enterprise SaaS":   ["enterprise saas", "b2b saas", "saas platform"],

    # --- Methodology / frameworks (engineering) ---
    "Microservices":     ["microservices", "micro-services", "micro services"],
    "Kubernetes":        ["kubernetes", "k8s"],
    "CI/CD":             ["ci/cd", "ci-cd", "continuous integration",
                         "continuous deployment"],
    "TDD":               ["tdd", "test-driven"],
    "Agile":             ["agile"],
}


# Build the inverse alias -> canonical map once, at module load.
_SKILL_ALIAS_TO_CANONICAL: Dict[str, str] = {}
for _canonical, _aliases in _SKILL_VOCAB.items():
    for _alias in _aliases:
        # First alias wins on collisions so canonical names (listed first)
        # are preferred over later aliases.
        _SKILL_ALIAS_TO_CANONICAL.setdefault(_alias.lower(), _canonical)


# Match an alias as a whole token (word-boundary) inside text. We use
# the longest-match-first strategy so "react native" is preferred
# over "react" when both substrings are present. Sort aliases by length
# descending; iterate and check word boundaries.
_SORTED_ALIASES: List[Tuple[str, str]] = sorted(
    _SKILL_ALIAS_TO_CANONICAL.items(), key=lambda kv: -len(kv[0]),
)


def _alias_in_text(alias: str, haystack_lower: str) -> bool:
    """Return True if ``alias`` appears in ``haystack_lower`` as a
    whole token (whitespace- or punctuation-bounded). Handles short
    aliases (< 4 chars) conservatively so 'go' doesn't match 'going'
    or 'ago'.
    """
    if not alias or not haystack_lower:
        return False
    # Aliases containing a space are phrase matches; only require that
    # the phrase appears as a substring (spaces already bound the
    # tokens). Single-word aliases use strict word boundaries.
    if " " in alias or "." in alias:
        return alias in haystack_lower
    # For very short tokens, require a whitespace or start/end boundary
    # on BOTH sides to avoid matching "go" inside "going" or "ago".
    start = 0
    n = len(alias)
    while True:
        idx = haystack_lower.find(alias, start)
        if idx < 0:
            return False
        before_ok = (idx == 0) or not haystack_lower[idx - 1].isalnum()
        after_ok = (
            idx + n >= len(haystack_lower)
            or not haystack_lower[idx + n].isalnum()
        )
        if before_ok and after_ok:
            return True
        start = idx + 1


def extract_skills_from_text(
    text: str,
    industry: str = "",
    max_skills: int = 15,
) -> List[str]:
    """RC-3 — deterministic skill extraction.

    Scan ``text`` (and optionally ``industry``) for occurrences of
    any alias in ``_SKILL_VOCAB``. Returns a deduplicated list of
    canonical skill names, ordered by the order they were declared in
    the vocabulary (longest alias first). Capped at ``max_skills``.

    Pure function. No LLM. No external APIs. No hallucination.
    Only terms that appear in the supplied text are returned.
    """
    if not text and not industry:
        return []
    haystack = " ".join([text or "", industry or ""]).lower()
    if not haystack.strip():
        return []

    found: List[str] = []
    seen: set = set()
    for alias, canonical in _SORTED_ALIASES:
        if canonical in seen:
            continue
        if _alias_in_text(alias, haystack):
            seen.add(canonical)
            found.append(canonical)
            if len(found) >= max_skills:
                break
    return found
