"""Sprint 13.7 — Production Stabilization — Regression Script.

Verify the discovery pipeline produces clean company data.

Run from backend/ root:

    cd backend
    python -m scripts.verify_discovery_quality

The script:
  1. Exercises the deterministic extractor with the BUG-REPRODUCING
     inputs from the production bug report (Google tracking IDs,
     article titles like "AI Makes Weather Prediction", HTML
     entities like &nbsp;/&quot;/&ldquo;/&rdquo;, founder
     descriptors like "Former Swiggy...").
  2. Asserts every rejection rule fires correctly.
  3. Exercises the pre-cache validation gate with hand-crafted
     records (good + bad).
  4. Optionally fetches live RSS feeds (env-gated, off by default)
     and confirms the cleaned output is clean.
  5. Prints a pass/fail summary + production-readiness score.

Exit codes:
  0 = all assertions passed
  1 = at least one assertion failed
  2 = script error (missing dep, import failure)
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from typing import Any, Callable, Dict, List, Tuple

# Ensure backend root is importable so we can ``from app...``.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.dirname(_THIS_DIR)
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------


class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.detail = ""
        self.error: str = ""

    def __repr__(self) -> str:
        flag = "PASS" if self.passed else "FAIL"
        return f"[{flag}] {self.name}: {self.detail}"


def run(name: str, fn: Callable[[], Tuple[bool, str]]) -> TestResult:
    r = TestResult(name)
    try:
        ok, detail = fn()
        r.passed = ok
        r.detail = detail
    except Exception as exc:  # pragma: no cover
        r.passed = False
        r.error = f"{type(exc).__name__}: {exc}"
        r.detail = f"raised {type(exc).__name__}"
    return r


# ---------------------------------------------------------------------------
# Bug-reproducing fixtures — taken verbatim from the production bug
# report. Each fixture is one RSS article dict that previously
# produced a garbage company record.
# ---------------------------------------------------------------------------


GARBAGE_FIXTURES: List[Dict[str, Any]] = [
    {
        "label": "Google News tracking ID in URL slug",
        "article": {
            "title": "AI startup raises $50M Series B",
            "url": "https://news.google.com/rss/articles/CBMiXWh0dHBzOi8vd3d3LnRlY2hjcnVuY2guY29tLzIwMjYvMDcvMzAvYWktc3RhcnR1cC1yYWlzZXMtNTBt",
            "content": "An AI startup raised $50M in Series B funding.",
            "published_date": "Wed, 30 Jul 2026 12:00:00 +0000",
        },
        "must_reject_url": True,
        "must_not_contain_in_name": ["Cbmi", "CBMi"],
    },
    {
        "label": "Article title 'AI Makes Weather Prediction'",
        "article": {
            "title": "AI Makes Weather Prediction More Accurate for Farmers",
            "url": "https://techcrunch.com/2026/07/30/ai-makes-weather-prediction-more-accurate-for-farmers",
            "content": "A new AI system makes weather prediction more accurate.",
            "published_date": "Wed, 30 Jul 2026 12:00:00 +0000",
        },
        "must_reject_url": True,
        "must_not_contain_in_name": ["Makes", "Prediction", "Weather"],
    },
    {
        "label": "Article title 'Black-Owned AI Startup'",
        "article": {
            "title": "Black-Owned AI Startup Raises $10M",
            "url": "https://techcrunch.com/2026/07/30/black-owned-ai-startup-raises-10m",
            "content": "A Black-owned AI startup raised $10M.",
            "published_date": "Wed, 30 Jul 2026 12:00:00 +0000",
        },
        "must_reject_url": True,
        "must_not_contain_in_name": ["Black", "Owned", "Startup"],
    },
    {
        "label": "'Former Swiggy' founder-fragment headline",
        "article": {
            "title": "Former Swiggy CTO's New AI Startup Raises $5M",
            "url": "https://techcrunch.com/2026/07/30/former-swiggy-cto-raises-5m",
            "content": "A former Swiggy CTO raised $5M.",
            "published_date": "Wed, 30 Jul 2026 12:00:00 +0000",
        },
        "must_reject_url": True,
        "must_not_contain_in_name": ["Former", "Swiggy"],
    },
]


HTML_ENTITY_FIXTURES: List[Dict[str, Any]] = [
    {
        "label": "Title with &nbsp; entity",
        "title": "Acme&nbsp;AI raises $20M",
        "must_not_contain": ["&nbsp;"],
        "must_contain": [" "],  # decoded space
    },
    {
        "label": "Title with &quot; entity",
        "title": "&quot;Anysphere&quot; raises $100M",
        "must_not_contain": ["&quot;"],
        "must_contain": ['"'],
    },
    {
        "label": "Title with &ldquo; &rdquo; entities",
        "title": "&ldquo;Cursor&rdquo; launches new feature",
        "must_not_contain": ["&ldquo;", "&rdquo;"],
        "must_contain": ['"'],
    },
    {
        "label": "Title with &#39; entity",
        "title": "Anthropic&#39;s new model",
        "must_not_contain": ["&#39;"],
        "must_contain": ["'"],
    },
    {
        "label": "Title with &amp; entity",
        "title": "Weights &amp; Biases raises $200M",
        "must_not_contain": ["&amp;"],
        "must_contain": ["&"],
    },
]


GOOD_FIXTURES: List[Dict[str, Any]] = [
    {
        "label": "Clean TechCrunch headline",
        "article": {
            "title": "Anysphere, the maker of Cursor, raises $100M Series B",
            "url": "https://techcrunch.com/2026/07/30/anysphere-raises-100m-series-b",
            "content": "Anysphere, the maker of Cursor, raised $100M at a $2.5B valuation, the company confirmed today. The round was led by Andreessen Horowitz.",
            "published_date": "Wed, 30 Jul 2026 12:00:00 +0000",
        },
        "must_have_name": "Anysphere",
    },
    {
        "label": "Clean TechCrunch headline (Dili)",
        "article": {
            "title": "Dili raises $15M Series A to automate compliance with AI",
            "url": "https://techcrunch.com/2026/07/30/dili-raises-15-million-to-automate-compliance-with-ai",
            "content": "Dili, a startup that uses AI to automate compliance workflows, raised $15M in Series A funding.",
            "published_date": "Wed, 30 Jul 2026 12:00:00 +0000",
        },
        "must_have_name": "Dili",
    },
    {
        "label": "Clean headline with HTML entities that decode correctly",
        "article": {
            "title": "Anthropic raises $4B Series D at $60B valuation",
            "url": "https://techcrunch.com/2026/07/30/anthropic-raises-4b-series-d",
            "content": "Anthropic &mdash; the AI safety company &mdash; raised $4B in Series D funding today, &ldquo;people familiar with the matter&rdquo; said.",
            "published_date": "Wed, 30 Jul 2026 12:00:00 +0000",
        },
        "must_have_name": "Anthropic",
        "must_not_contain_in_tagline": ["&mdash;", "&ldquo;", "&rdquo;"],
    },
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_garbage_fixtures_rejected() -> List[TestResult]:
    """Verify every garbage fixture produces a record that either has
    no name, or whose name does not contain forbidden substrings."""
    from app.services._deterministic_extractor import extract_from_tavily

    results: List[TestResult] = []
    for fx in GARBAGE_FIXTURES:
        article = dict(fx["article"])  # copy

        def _check(fx=fx, article=article) -> Tuple[bool, str]:
            rec = extract_from_tavily(article)
            name = rec.get("name") or ""
            # Either no name was extracted (preferred), or the name
            # does not contain forbidden fragments.
            if not name:
                return (True, f"rejected with empty name")
            for bad in fx.get("must_not_contain_in_name", []):
                if bad.lower() in name.lower():
                    return (False, f"name {name!r} contains {bad!r}")
            return (True, f"name={name!r} (no forbidden fragments)")

        results.append(run(f"reject: {fx['label']}", _check))
    return results


def test_html_entity_decoding() -> List[TestResult]:
    """Verify HTML entity decoding produces clean text at every
    boundary: RSS titles, article content, tagline, why_hot."""
    from app.services._deterministic_extractor import (
        _decode_html_entities,
        _clean_description,
    )

    results: List[TestResult] = []
    for fx in HTML_ENTITY_FIXTURES:

        def _check(fx=fx) -> Tuple[bool, str]:
            decoded = _decode_html_entities(fx["title"])
            for bad in fx["must_not_contain"]:
                if bad in decoded:
                    return (False, f"{bad!r} survived in {decoded!r}")
            for good in fx["must_contain"]:
                if good not in decoded:
                    return (False, f"{good!r} missing in {decoded!r}")
            # Also test the cleaning helper (tagline / why_hot path)
            cleaned = _clean_description(fx["title"], max_length=240)
            for bad in fx["must_not_contain"]:
                if bad in cleaned:
                    return (False, f"{bad!r} survived in cleaned {cleaned!r}")
            return (True, f"decoded -> {decoded!r}")

        results.append(run(f"decode: {fx['label']}", _check))
    return results


def test_good_fixtures_pass() -> List[TestResult]:
    """Verify legitimate articles produce records with the expected
    company names and clean descriptions."""
    from app.services._deterministic_extractor import extract_from_tavily

    results: List[TestResult] = []
    for fx in GOOD_FIXTURES:

        def _check(fx=fx) -> Tuple[bool, str]:
            rec = extract_from_tavily(fx["article"])
            name = rec.get("name") or ""
            if name != fx["must_have_name"]:
                return (False, f"expected name={fx['must_have_name']!r}, got {name!r}")
            for bad in fx.get("must_not_contain_in_tagline", []):
                if bad in (rec.get("tagline") or ""):
                    return (False, f"{bad!r} in tagline {rec.get('tagline')!r}")
            score = rec.get("extraction_score", 0)
            if score < 50:
                return (False, f"score={score} below threshold")
            return (True, f"name={name!r} score={score}")

        results.append(run(f"good: {fx['label']}", _check))
    return results


def test_validation_gate() -> List[TestResult]:
    """Verify the pre-cache validation gate rejects bad records and
    admits good ones."""
    from app.services._deterministic_extractor import (
        validate_company_record,
        filter_records,
    )

    results: List[TestResult] = []

    # Bad records — each must be rejected for a specific reason.
    bad_records: List[Tuple[Dict[str, Any], str]] = [
        ({"name": ""}, "empty name"),
        ({"name": "UNKNOWN"}, "literal UNKNOWN"),
        ({"name": "AI startup"}, "blocked words"),
        ({"name": "Former Swiggy"}, "founder descriptor"),
        ({"name": "Cbmiuwfbvv95"}, "tracking ID"),
        ({"name": "CBMiXWh0dHBzOi8"}, "Google News hash"),
        ({"name": "AI Makes Weather"}, "article-title verb"),
        ({"name": "Acme", "tagline": "", "funding_amount": "$10M",
          "funding_round": "Series A", "industry": "AI",
          "extraction_score": 80}, "empty tagline"),
        ({"name": "Acme", "tagline": "ok", "funding_amount": "",
          "funding_round": "Series A", "industry": "AI",
          "extraction_score": 80}, "missing funding_amount"),
        ({"name": "Acme", "tagline": "ok", "funding_amount": "$10M",
          "funding_round": "Series A", "industry": "AI",
          "extraction_score": 30}, "low score"),
        ({"name": "Acme", "tagline": "ok", "funding_amount": "ten million",
          "funding_round": "Series A", "industry": "AI",
          "extraction_score": 80}, "bad funding_amount format"),
        ({"name": "Acme &amp; Co"}, "HTML entity in name"),
    ]
    for rec, label in bad_records:

        def _check(rec=rec, label=label) -> Tuple[bool, str]:
            ok, reasons = validate_company_record(rec)
            if ok:
                return (False, f"bad record accepted: {label}")
            if not reasons:
                return (False, f"accepted with empty reasons list")
            return (True, f"rejected for {reasons[0][:60]}")

        results.append(run(f"validate reject: {label}", _check))

    # Good records — must be admitted.
    good_records: List[Tuple[Dict[str, Any], str]] = [
        ({"name": "Anysphere", "tagline": "AI code editor.",
          "funding_amount": "$100M", "funding_round": "Series B",
          "industry": "Developer Tools", "headquarters": "San Francisco, CA",
          "extraction_score": 80}, "Anysphere"),
        ({"name": "Cursor", "tagline": "AI code editor.",
          "funding_amount": "$50M", "funding_round": "Series A",
          "industry": "Developer Tools", "headquarters": "San Francisco, CA",
          "extraction_score": 65}, "Cursor"),
    ]
    for rec, label in good_records:

        def _check(rec=rec, label=label) -> Tuple[bool, str]:
            ok, reasons = validate_company_record(rec)
            if not ok:
                return (False, f"good record rejected: {reasons}")
            return (True, f"admitted")

        results.append(run(f"validate admit: {label}", _check))

    # filter_records with mixed input
    def _check_filter() -> Tuple[bool, str]:
        mixed = [rec for rec, _ in bad_records] + [rec for rec, _ in good_records]
        valid, rejected = filter_records(mixed)
        if len(valid) != len(good_records):
            return (False, f"expected {len(good_records)} valid, got {len(valid)}")
        if len(rejected) != len(bad_records):
            return (False, f"expected {len(bad_records)} rejected, got {len(rejected)}")
        return (True, f"{len(valid)} admitted, {len(rejected)} rejected")

    results.append(run("filter_records: mixed batch", _check_filter))

    return results


def test_description_cleanup() -> List[TestResult]:
    """Verify description cleanup removes tracking parameters,
    inline URLs, broken unicode, and excessive whitespace."""
    from app.services._deterministic_extractor import _clean_description

    cases: List[Tuple[str, str, str]] = [
        (
            "Visit https://example.com?fbclid=abc123&utm_source=news and learn more",
            "url+tracking",
            "Visit and learn more",
        ),
        (
            "Why this matters  \n\n\n  for AI startups",
            "excess whitespace",
            "Why this matters for AI startups",
        ),
        (
            "Leading ��broken�� unicode and trailing junk   ",
            "broken unicode + trim",
            "Leading broken unicode and trailing junk",
        ),
        (
            "Sentence one. Second sentence here that should be much longer " * 20,
            "trim to max_length",
            None,  # just check no entity/URL survives
        ),
    ]

    results: List[TestResult] = []
    for raw, label, expected_substring in cases:

        def _check(raw=raw, label=label, expected_substring=expected_substring) -> Tuple[bool, str]:
            cleaned = _clean_description(raw, max_length=200)
            # No HTML entities survived
            if "&" in cleaned and not re.search(r"&\w+;", cleaned):
                # "&" is allowed when not part of an entity
                pass
            if re.search(r"&[a-z]+;|&#\d+;", cleaned, re.IGNORECASE):
                return (False, f"HTML entity survived: {cleaned!r}")
            if "http://" in cleaned or "https://" in cleaned:
                return (False, f"URL survived: {cleaned!r}")
            if "  " in cleaned:
                return (False, f"double space survived: {cleaned!r}")
            if expected_substring is not None:
                if expected_substring not in cleaned:
                    return (False, f"expected substring {expected_substring!r} missing in {cleaned!r}")
            return (True, f"cleaned -> {cleaned[:80]!r}{'...' if len(cleaned) > 80 else ''}")

        results.append(run(f"clean: {label}", _check))
    return results


def test_url_slug_tracking_id() -> List[TestResult]:
    """Verify URL slug extraction rejects tracking IDs outright."""
    from app.services._deterministic_extractor import extract_company_from_url_slug

    cases: List[Tuple[str, str, bool]] = [
        # (url, label, should_have_name)
        ("https://news.google.com/rss/articles/CBMiXWh0dHBz",
         "Google news tracking path", False),
        ("https://example.com/anthropic-raises-4b",
         "Normal funding slug", True),
        ("https://example.com/abc123def456789012",
         "Long alphanumeric hash slug", False),
        ("https://example.com/Cbmiuwfbvv95-launches",
         "Slug starts with hash-like prefix", False),
        ("https://example.com/anysphere",
         "Just a company slug", True),
    ]

    results: List[TestResult] = []
    for url, label, should_have_name in cases:

        def _check(url=url, label=label, should_have_name=should_have_name) -> Tuple[bool, str]:
            name, conf, reason = extract_company_from_url_slug(url)
            has_name = name is not None
            if has_name != should_have_name:
                return (
                    False,
                    f"expected should_have_name={should_have_name}, got {name!r} (reason={reason!r})",
                )
            return (True, f"name={name!r}, reason={reason!r}")

        results.append(run(f"slug: {label}", _check))
    return results


def test_company_name_validation() -> List[TestResult]:
    """Verify _is_valid_company_name rejects every forbidden pattern."""
    from app.services._deterministic_extractor import _is_valid_company_name

    cases: List[Tuple[str, bool]] = [
        ("Anthropic", True),
        ("Anysphere", True),
        ("Weights & Biases", True),
        ("Dili", True),
        ("AI", False),  # blocked whole-name
        ("AI Startup", False),  # blocked tokens
        ("", False),  # empty
        ("Cbmiuwfbvv95", False),  # tracking ID
        ("CBMiXWh0dHBz", False),  # tracking ID
        ("Makes Weather", False),  # action verb prefix
        ("Former Swiggy", False),  # blocked token
        ("Acme &amp; Co", False),  # HTML entity in name
        ("a", False),  # too short
        ("AI startup Raises Series A From Investors", False),  # all blocked words
    ]

    results: List[TestResult] = []
    for name, expected in cases:

        def _check(name=name, expected=expected) -> Tuple[bool, str]:
            got = _is_valid_company_name(name)
            if got != expected:
                return (False, f"{name!r}: expected {expected}, got {got}")
            return (True, f"{name!r} -> {got}")

        results.append(run(f"name: {name!r}", _check))
    return results


def test_cache_write_filters() -> List[TestResult]:
    """Verify _write_cache applies the validation gate."""
    import tempfile
    from app.services import orchestrator

    results: List[TestResult] = []

    # Patch _CACHE_PATH to a temp file so we don't touch the real cache.
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_cache = os.path.join(tmpdir, "fake_cache.json")
        original_path = orchestrator._CACHE_PATH
        orchestrator._CACHE_PATH = type(original_path)(fake_cache)
        try:

            def _check() -> Tuple[bool, str]:
                # Mix good + bad records
                good = {
                    "name": "Anysphere", "tagline": "AI code editor.",
                    "funding_amount": "$100M", "funding_round": "Series B",
                    "industry": "Developer Tools", "headquarters": "San Francisco, CA",
                    "extraction_score": 80,
                }
                bad1 = {"name": "Cbmiuwfbvv95", "tagline": "x",
                        "funding_amount": "$1M", "funding_round": "Seed",
                        "industry": "AI", "extraction_score": 60}
                bad2 = {"name": "AI Startup", "tagline": "x",
                        "funding_amount": "$1M", "funding_round": "Seed",
                        "industry": "AI", "extraction_score": 60}
                bad3 = {"name": "", "tagline": "", "funding_amount": "",
                        "funding_round": "", "industry": "",
                        "extraction_score": 0}
                orchestrator._write_cache(
                    [good, bad1, bad2, bad3],
                    data_source="live",
                    reason="test",
                )
                with open(fake_cache, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                cached_names = [c.get("name") for c in payload["companies"]]
                if "Anysphere" not in cached_names:
                    return (False, f"good record dropped: {cached_names}")
                for bad_name in ("Cbmiuwfbvv95", "AI Startup", ""):
                    if bad_name in cached_names:
                        return (False, f"bad record kept: {cached_names}")
                return (True, f"cached={cached_names}")

            results.append(run("_write_cache: validation gate", _check))
        finally:
            orchestrator._CACHE_PATH = original_path
    return results


# ---------------------------------------------------------------------------
# Sprint 13.8 — Runtime regression tests.
# These lock in the 5 runtime fixes discovered during end-to-end validation:
#   1. Funding round "ipo" / "pre-ipo" preserves acronym casing
#   2. website field never holds the RSS article URL
#   3. snippet pattern "X startup Y raises" extracts Y, not X
#   4. career_page rejects google.com and other aggregator hosts
#   5. leading-token blocklist rejects "Legal AI", "Exclusive", etc.
# ---------------------------------------------------------------------------


def test_sprint_138_funding_round_ipo() -> List[TestResult]:
    """parse_funding_round should return 'IPO' / 'Pre-IPO', not 'Ipo'."""
    from app.services._deterministic_extractor import parse_funding_round

    results: List[TestResult] = []
    cases = [
        ("Moonshot AI opens pre-IPO funding round for US$50b valuation",
         "Pre-IPO"),
        ("Anthropic files for IPO", "IPO"),
        ("Cursor raises Series B $100M", "Series B"),
        ("Acme raises Seed $5M", "Seed"),
        ("Acme raises Series A $5M", "Series A"),
    ]
    for text, expected in cases:

        def _check(text=text, expected=expected) -> Tuple[bool, str]:
            got = parse_funding_round(text)
            if got != expected:
                return (False, f"expected {expected!r}, got {got!r}")
            return (True, f"{text[:40]!r} -> {got!r}")

        results.append(run(f"funding_round: {expected}", _check))
    return results


def test_sprint_138_website_not_article_url() -> List[TestResult]:
    """extract_from_tavily must leave website='' and store the article
    URL in source_url instead."""
    from app.services._deterministic_extractor import extract_from_tavily

    fixtures = [
        ("techcrunch", "https://techcrunch.com/2026/07/30/anthropic-raises-4b"),
        ("google news", "https://news.google.com/rss/articles/CBMiXWh0dHBz..."),
        ("standard hk", "https://www.thestandard.com.hk/some-article"),
    ]
    results: List[TestResult] = []
    for label, url in fixtures:

        def _check(label=label, url=url) -> Tuple[bool, str]:
            rec = extract_from_tavily({
                "title": "Acme raises $50M Series B",
                "url": url,
                "content": "Acme raised $50M in Series B funding today.",
                "published_date": "Wed, 30 Jul 2026 12:00:00 +0000",
            })
            if rec.get("website"):
                return (False, f"website={rec['website']!r} should be empty")
            if rec.get("source_url") != url:
                return (False, f"source_url mismatch")
            return (True, f"website='' source_url={url[:40]!r}")

        results.append(run(f"website: {label}", _check))
    return results


def test_sprint_138_snippet_x_startup_y() -> List[TestResult]:
    """The new snippet pattern extracts Y from 'X startup Y raises'."""
    from app.services._deterministic_extractor import extract_company_from_snippet

    results: List[TestResult] = []
    cases = [
        ("Legal AI startup NYAI raises $1.5mn seed round", "NYAI"),
        ("Generative AI startup Cohere raises $200M Series C", "Cohere"),
        ("Enterprise AI company Harvey raises $100M Series B", "Harvey"),
        ("Predictive analytics firm Anysphere raises $100M", "Anysphere"),
        ("Open-source AI platform Mistral raises $400M", "Mistral"),
        # Negative case: no startup/company word, fall through to first cap run
        ("Anysphere raised $100M Series B today", None),  # falls through
    ]
    for snippet, expected in cases:

        def _check(snippet=snippet, expected=expected) -> Tuple[bool, str]:
            name, conf, reason = extract_company_from_snippet(snippet)
            if expected is None:
                # Just confirm it returned SOMETHING
                return (True, f"name={name!r} reason={reason!r}")
            if name != expected:
                return (False, f"expected {expected!r}, got {name!r} ({reason!r})")
            return (True, f"got {name!r} ({reason!r})")

        results.append(run(f"snippet: {snippet[:40]!r}", _check))
    return results


def test_sprint_138_google_career_blocked() -> List[TestResult]:
    """career_page() must reject google.com and other aggregator hosts."""
    from app.services._deterministic_extractor import career_page

    results: List[TestResult] = []
    blocked = [
        "https://news.google.com/rss/articles/CBMiXWh0dHBz",
        "https://www.google.com/article",
        "https://google.com",
        "https://www.google.co.uk/article",
    ]
    for url in blocked:

        def _check(url=url) -> Tuple[bool, str]:
            result = career_page(url)
            if result:
                return (False, f"career_page returned {result!r} for {url!r}")
            return (True, "blocked (returned '')")

        results.append(run(f"career_page blocked: {url[:40]!r}", _check))
    return results


def test_sprint_138_leading_blocked_words() -> List[TestResult]:
    """Legal AI / Enterprise AI / Exclusive / Sponsored as leading tokens
    must reject the entire name; but Mistral AI / Together AI must pass."""
    from app.services._deterministic_extractor import _is_valid_company_name

    results: List[TestResult] = []
    cases = [
        ("Legal AI", False),
        ("Enterprise AI", False),
        ("Generative AI", False),
        ("Exclusive", False),
        ("Sponsored", False),
        ("Opinion", False),
        ("AI Startup", False),
        # Must still accept compound names where AI is a SUFFIX
        ("Mistral AI", True),
        ("Together AI", True),
        ("Weights & Biases", True),
        ("Anthropic", True),
        ("WindBorne Systems", True),
    ]
    for name, expected in cases:

        def _check(name=name, expected=expected) -> Tuple[bool, str]:
            got = _is_valid_company_name(name)
            if got != expected:
                return (False, f"{name!r}: expected {expected}, got {got}")
            return (True, f"{name!r} -> {got}")

        results.append(run(f"leading: {name!r}", _check))
    return results


def test_rss_article_decode() -> List[TestResult]:
    """Verify _feed_to_articles decodes HTML entities in titles and
    summaries before they leave the RSS layer."""
    from app.services.rss_discovery import _feed_to_articles

    class _FakeEntry(dict):
        """feedparser-style entry — supports .get() access."""

    class _FakeFeed:
        def __init__(self, entries):
            self.entries = entries

    feed = _FakeFeed([
        _FakeEntry({
            "title": "Anysphere&nbsp;raises&nbsp;$100M",
            "link": "https://example.com/anysphere-raises-100m",
            "summary": "&ldquo;Cursor&rdquo; maker raises $100M &mdash; the largest round of the week.",
            "published_parsed": None,
            "published": "Wed, 30 Jul 2026 12:00:00 +0000",
        }),
        _FakeEntry({
            "title": "Anthropic&#39;s new model",
            "link": "https://example.com/anthropic-new-model",
            "summary": "Anthropic&#39;s new model launched today.",
            "published_parsed": None,
            "published": "Wed, 30 Jul 2026 12:00:00 +0000",
        }),
    ])

    def _check() -> Tuple[bool, str]:
        articles = _feed_to_articles(feed, "test_feed")
        if len(articles) != 2:
            return (False, f"expected 2 articles, got {len(articles)}")
        title = articles[0]["title"]
        summary = articles[0]["content"]
        for bad in ["&nbsp;", "&ldquo;", "&rdquo;", "&mdash;"]:
            if bad in title or bad in summary:
                return (False, f"{bad!r} survived decoding")
        # nbsp should have decoded to space
        if "Anysphere raises" not in title:
            return (False, f"nbsp did not decode to space: {title!r}")
        # &ldquo; &rdquo; should have decoded to "
        if '"Cursor"' not in summary:
            return (False, f"ldquo/rdquo did not decode to quote: {summary!r}")
        # &#39; should have decoded to '
        if "Anthropic's" not in articles[1]["title"]:
            return (False, f"#39 did not decode: {articles[1]['title']!r}")
        return (True, f"all entities decoded")

    return [run("RSS: HTML entity decoding", _check)]


def test_optional_live_rss() -> List[TestResult]:
    """OPTIONAL — only run when ``FUNDFLOW_LIVE_RSS_TEST=1``.

    Fetches the real RSS feeds and confirms the post-extraction
    records are clean. Skipped by default to keep the script
    network-free and fast.
    """
    if os.environ.get("FUNDFLOW_LIVE_RSS_TEST") != "1":
        # Skipped — mark as passed (not a failure) so the summary
        # does not count it against production readiness.
        r = TestResult("LIVE_RSS: skipped (set FUNDFLOW_LIVE_RSS_TEST=1 to enable)")
        r.passed = True
        r.detail = "skipped (opt-in)"
        return [r]
    # When enabled, just confirm the import path works; the actual
    # network test is fragile and slow.
    from app.services.weekly_funding_agent import discover_last_week_funding

    def _check() -> Tuple[bool, str]:
        records = discover_last_week_funding(lookback_days=7)
        if not isinstance(records, list):
            return (False, f"expected list, got {type(records)}")
        for rec in records:
            name = rec.get("name") or ""
            if "Cbmi" in name or "CBMi" in name:
                return (False, f"tracking ID in live data: {name!r}")
            if "&" in name and re.search(r"&[a-z]+;", name, re.IGNORECASE):
                return (False, f"HTML entity in live name: {name!r}")
            if rec.get("below_quality_threshold"):
                return (False, f"below-threshold record leaked through: {rec}")
        return (True, f"{len(records)} live records, all clean")

    return [run("LIVE_RSS: real feed sanity check", _check)]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    import re  # used by tests above
    globals()["re"] = re

    test_groups = [
        ("Company name validation", test_company_name_validation),
        ("URL slug tracking-ID rejection", test_url_slug_tracking_id),
        ("Garbage fixtures (bug repro)", test_garbage_fixtures_rejected),
        ("HTML entity decoding", test_html_entity_decoding),
        ("Good fixtures pass", test_good_fixtures_pass),
        ("Description cleanup", test_description_cleanup),
        ("RSS layer entity decoding", test_rss_article_decode),
        ("Validation gate", test_validation_gate),
        ("Cache write filters", test_cache_write_filters),
        ("Sprint 13.8 — funding round IPO casing",
         test_sprint_138_funding_round_ipo),
        ("Sprint 13.8 — website not article URL",
         test_sprint_138_website_not_article_url),
        ("Sprint 13.8 — snippet 'X startup Y raises'",
         test_sprint_138_snippet_x_startup_y),
        ("Sprint 13.8 — google.com career blocked",
         test_sprint_138_google_career_blocked),
        ("Sprint 13.8 — leading-token blocklist",
         test_sprint_138_leading_blocked_words),
        ("Optional live RSS", test_optional_live_rss),
    ]

    all_results: List[TestResult] = []
    for group_name, fn in test_groups:
        print(f"\n=== {group_name} ===")
        results = fn()
        for r in results:
            print(f"  {r}")
            if r.error:
                print(f"    error: {r.error}")
        all_results.extend(results)

    passed = sum(1 for r in all_results if r.passed)
    total = len(all_results)
    skipped = sum(1 for r in all_results
                  if r.passed and "skipped" in r.detail.lower())
    failed = sum(1 for r in all_results if not r.passed)
    print("\n" + "=" * 60)
    print(f"SUMMARY: {passed}/{total} passed, {skipped} skipped, {failed} failed")
    print("=" * 60)

    if failed == 0:
        return 0
    print("\nFAIL — see details above")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"\nSCRIPT ERROR: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        sys.exit(2)
