"""Orchestrator service - coordinates the weekly career report workflow.

This is the foundation module that all future AI services plug into.
Currently produces personalized reports from real-world AI startup
discovery (Tavily + Firecrawl + OpenAI), with a local cache and a
Demo Data fallback when discovery is unavailable.
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.resume import Resume
from app.services.generation_service import generate_cover_letter
from app.services.intelligence import career_intelligence, market_intelligence

logger = logging.getLogger("fundflow")

_SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "seed_companies.json"
_CACHE_DIR = Path(os.environ.get("FUNDFLOW_DATA_DIR", Path(__file__).resolve().parent.parent)) / "cache"
# Backwards-compat: if the env var isn't set, fall back to the historical
# location (next to the app/ folder). Production deployments should set
# FUNDFLOW_DATA_DIR to a persistent volume path.
_CACHE_PATH = _CACHE_DIR / "latest_discovery.json"


def _log_stage(name: str, duration: float) -> None:
    """Log a workflow stage boundary. No side effect beyond logging.

    Kept for observability — operators can grep the log for stage
    boundaries to reconstruct timing. The ``duration`` argument is the
    cumulative elapsed time at the point this stage completed.
    """
    logger.info("[Workflow] %s (%.2fs)", name, duration)


def _load_seed_companies() -> List[Dict[str, Any]]:
    """Load the curated Demo Data set of funded AI startups.

    Used as the fallback when no cache exists and discovery fails.
    """
    with open(_SEED_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _read_cache() -> Optional[Dict[str, Any]]:
    """Return cached discovery if it exists and is fresh, else None with metadata.

    Tolerates BOTH the legacy flat-list format (``[{...}, {...}]``)
    and the current envelope format (``{"companies": [...],
    "metadata": {...}}``). The legacy list is normalised into the
    envelope on read so downstream code can always rely on the
    envelope shape.
    """
    if not _CACHE_PATH.exists():
        return None
    age_hours = (time.time() - _CACHE_PATH.stat().st_mtime) / 3600.0
    if age_hours >= settings.DISCOVERY_CACHE_HOURS:
        return None
    try:
        with open(_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("companies"), list):
            # Current envelope format.
            logger.info(
                "Using cached discovery (%d companies, %.1fh old, source=%s)",
                len(data["companies"]),
                age_hours,
                data.get("metadata", {}).get("data_source", "unknown"),
            )
            # Merge read-time metadata with the persisted metadata.
            persisted_meta = data.get("metadata") or {}
            return {
                "companies": data["companies"],
                "metadata": {
                    **persisted_meta,
                    "cache_hit": True,
                    "age_hours": round(age_hours, 2),
                    "cached_at": persisted_meta.get(
                        "cached_at", time.ctime(_CACHE_PATH.stat().st_mtime)
                    ),
                    "cache_path": str(_CACHE_PATH),
                },
            }
        if isinstance(data, list) and data:
            # Legacy flat-list format — normalise to envelope.
            logger.info(
                "Using cached discovery in legacy flat-list format "
                "(%d companies, %.1fh old)",
                len(data),
                age_hours,
            )
            return {
                "companies": data,
                "metadata": {
                    "cache_hit": True,
                    "age_hours": round(age_hours, 2),
                    "cached_at": time.ctime(_CACHE_PATH.stat().st_mtime),
                    "cache_path": str(_CACHE_PATH),
                    "data_source": "unknown",
                    "reason": "legacy cache (flat-list format)",
                    "fallback": False,
                },
            }
    except Exception as exc:
        logger.warning("Failed to read discovery cache: %s", exc)
    return None


def _write_cache(
    companies: Any,
    data_source: str = "live",
    reason: str = "",
) -> Dict[str, Any]:
    """Persist discovered companies to the cache file with metadata.

    Always writes a dict envelope so the cache can carry
    cross-cutting fields (recommendations_resume_id,
    recommendations_generated_at, etc.) alongside the company list.
    Reads any existing envelope to preserve those fields across
    discovery overwrites.

    The ``companies`` parameter may be either:
      * a list of company dicts (the common case), or
      * a pre-built envelope dict ``{"companies": [...], "metadata":
        {...}}`` (legacy callers like ``run_enrichment``).

    Either form is normalised to a list before persisting.

    ``data_source`` records whether the cache holds real live
    discoveries (``"live"``) or curated seed fallback (``"seed"``).
    ``reason`` is a free-text explanation of why this write happened
    (e.g. ``"successful Tavily discovery for window YYYY-MM-DD..YYYY-MM-DD"``
    or ``"first deployment: Tavily failed; seeded for non-empty UI"``).

    Defaults to ``data_source="live"`` so existing callers behave
    identically; only explicit seed initialisation passes
    ``data_source="seed"``.
    """
    # Normalise legacy envelope-dict input to a plain list.
    if isinstance(companies, dict) and isinstance(companies.get("companies"), list):
        companies = companies["companies"]
    elif not isinstance(companies, list):
        companies = list(companies) if companies else []

    # Sprint 13.7 — Production Stabilization — Data Quality.
    # Pre-cache validation gate. Drop records whose required fields
    # are missing or whose extraction score is below the quality
    # threshold. This is defense-in-depth: the weekly funding agent
    # already runs ``filter_records`` before this point, but the
    # cache writer is the single chokepoint for every discovery
    # pathway (weekly agent, first-deployment live discovery,
    # enrichment refresh). Validating here means garbage cannot
    # land in the cache no matter who calls it.
    #
    # RC-1 — skip the gate for seed records. The curated seed
    # dataset (20 static companies) has no ``extraction_score``
    # because it never went through the RSS pipeline, and writing
    # it as ``[]`` after filtering would corrupt the cache exactly
    # as it did on this sprint. RSS records still pass through the
    # gate unchanged.
    if data_source != "seed":
        try:
            from app.services._deterministic_extractor import filter_records
            before = len(companies)
            valid, rejected = filter_records(companies)
            if rejected:
                logger.info(
                    "_write_cache: rejected %d/%d records at validation gate",
                    len(rejected),
                    before,
                )
            companies = valid
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("_write_cache: validation gate skipped: %s", exc)

    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        existing: Dict[str, Any] = {}
        try:
            with open(_CACHE_PATH, "r", encoding="utf-8") as f:
                prior = json.load(f)
            if isinstance(prior, dict):
                existing = prior
        except Exception:
            existing = {}
        envelope = {
            "companies": companies,
            "metadata": {
                **existing.get("metadata", {}),
                "cache_hit": False,
                "cached_at": time.time(),
                "cache_path": str(_CACHE_PATH),
                "companies_count": len(companies),
                "data_source": data_source,
                "reason": reason or "",
                "fallback": data_source == "seed",
            },
        }
        # NOTE: this envelope is GLOBAL — one file shared by every user.
        # Nothing resume-derived may be written into it. Two legacy keys
        # (``recommendations_resume_id``, ``recommendations_generated_at``)
        # used to be copied forward from any prior envelope here. No code
        # writes them, no live cache contains them, and carrying a resume
        # id in a shared file is exactly the class of bug this migration
        # exists to remove — so the copy-forward is gone. Per-company
        # recommendations are computed per-request in the companies route
        # and attached to a request-local copy.
        with open(_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(envelope, f, indent=2)
        # Now that the file exists, populate cached_at_human from its
        # mtime so the human-readable timestamp matches the actual
        # file write.
        envelope["metadata"]["cached_at_human"] = time.ctime(
            _CACHE_PATH.stat().st_mtime
        )
        logger.info(
            "Cached %d discovered companies (data_source=%s)",
            len(companies), data_source,
        )
        return {
            "cache_hit": False,
            "cached_at": envelope["metadata"]["cached_at_human"],
            "cache_path": str(_CACHE_PATH),
            "companies_count": len(companies),
            "data_source": data_source,
            "fallback": data_source == "seed",
        }
    except Exception as exc:
        logger.warning("Failed to write discovery cache: %s", exc)
        return {"cache_hit": False, "error": str(exc)}


def invalidate_cache() -> bool:
    """Manually invalidate the discovery cache."""
    try:
        if _CACHE_PATH.exists():
            _CACHE_PATH.unlink()
            logger.info("Discovery cache invalidated")
            return True
        return False
    except Exception as exc:
        logger.warning("Failed to invalidate cache: %s", exc)
        return False


def trigger_weekly_refresh(force: bool = False) -> Dict[str, Any]:
    """Thin wrapper exposed for the admin route and for tests.

    Delegates to ``weekly_funding_agent.run_weekly_refresh``. Lives
    here (not in the agent module) so callers that already import
    orchestrator helpers can also drive the agent without adding
    a new dependency. The cache file path is the synchronization
    point — concurrent calls are safe.
    """
    from app.services.weekly_funding_agent import run_weekly_refresh

    return run_weekly_refresh(force=force)


def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics and health information."""
    if not _CACHE_PATH.exists():
        return {
            "exists": False,
            "age_hours": 0,
            "size_bytes": 0,
            "status": "no_cache",
        }
    
    try:
        stat = _CACHE_PATH.stat()
        age_hours = (time.time() - stat.st_mtime) / 3600.0
        is_fresh = age_hours < settings.DISCOVERY_CACHE_HOURS
        
        with open(_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        return {
            "exists": True,
            "age_hours": round(age_hours, 2),
            "size_bytes": stat.st_size,
            "is_fresh": is_fresh,
            "status": "fresh" if is_fresh else "stale",
            "companies_count": len(data) if isinstance(data, list) else 0,
            "cached_at": time.ctime(stat.st_mtime),
            "cache_path": str(_CACHE_PATH),
        }
    except Exception as exc:
        logger.warning("Failed to get cache stats: %s", exc)
        return {
            "exists": True,
            "status": "error",
            "error": str(exc),
        }


def _run_discovery() -> List[Dict[str, Any]]:
    """Run the live RSS discovery pipeline. Raises on any failure.

    RC-1 — delegate to the Sprint-9 RSS pipeline
    (``weekly_funding_agent.discover_last_week_funding``) instead
    of the legacy Tavily discovery module. The legacy module
    references ``settings.TAVILY_API_KEY`` which no longer exists,
    raising AttributeError on every call. The RSS pipeline is the
    only live discovery path we ship today.
    """
    from app.services.weekly_funding_agent import discover_last_week_funding

    companies = discover_last_week_funding()
    if not companies:
        raise RuntimeError("Discovery returned no companies")
    return companies


def _load_companies() -> List[Dict[str, Any]]:
    """Smart loader: cache -> live discovery -> first-deployment seed.

    Never raises. Always returns a non-empty list of companies.

    Production-safety rule (Ticket-CRITICAL-1): real live discoveries
    are NEVER silently overwritten by the curated seed dataset. The
    seed fallback is only allowed on first deployment — i.e. when no
    cache file exists yet.

    - **Cache hit with live data** → return cached companies verbatim.
    - **Cache hit with seed data** → return cached seed verbatim (do
      NOT attempt live re-discovery here; that is the weekly
      scheduler's job).
    - **Cache miss + live discovery succeeds** → write + return live
      data with ``data_source="live"``.
    - **Cache miss + live discovery fails** → write + return seed with
      ``data_source="seed"`` (acceptable only because no real data
      exists yet to lose).
    """
    cached = _read_cache()
    if cached is not None and cached.get("companies"):
        # Existing cache is authoritative. Return its companies verbatim,
        # regardless of data_source. The caller can inspect metadata to
        # decide whether to surface "seed fallback" UI hints.
        return cached["companies"] if isinstance(cached, dict) else cached

    # RC-1 — a cache file that contains an empty ``companies`` list is
    # corrupt (e.g. written by an older version of the validation
    # gate that filtered seed records to ``[]``). Treat it as a cache
    # miss and regenerate. This also keeps the documented contract
    # "Always returns a non-empty list of companies" intact.
    if cached is not None and not cached.get("companies"):
        logger.warning(
            "Cached discovery is empty; treating as cache miss and "
            "regenerating (this should be a one-time recovery)"
        )
        invalidate_cache()

    # No cache exists — this is first deployment (or the cache was
    # manually invalidated). Live discovery is permitted; if it fails,
    # the seed fallback is acceptable because there is no real data to
    # overwrite.
    try:
        companies = _run_discovery()
        _write_cache(
            companies,
            data_source="live",
            reason="successful live discovery (first deployment)",
        )
        return companies
    except Exception as exc:
        logger.warning(
            "Live discovery unavailable on first deployment (%s); "
            "initialising cache with curated seed data. This fallback "
            "will be replaced on the next successful weekly refresh.",
            exc,
        )
        seed = _load_seed_companies()
        _write_cache(
            seed,
            data_source="seed",
            reason=(
                "first deployment: live discovery failed (%s); seeded "
                "for non-empty UI" % exc
            ),
        )
        return seed


def _aggregate_skills(lists: List[List[str]]) -> List[str]:
    """Merge multiple skill lists into one deduplicated, normalized set.

    - Removes duplicates (case-insensitive)
    - Ignores empty / whitespace-only values
    - Trims whitespace on each entry
    - Preserves the original casing of the first occurrence for UI display
      (e.g. "FastAPI" stays "FastAPI", not "Fastapi")
    """
    seen: Dict[str, str] = {}
    for lst in lists:
        if not lst:
            continue
        for item in lst:
            if not isinstance(item, str):
                continue
            v = item.strip()
            if not v:
                continue
            key = v.lower()
            if key not in seen:
                seen[key] = v
    return list(seen.values())


def _build_candidate(resume: Resume) -> Dict[str, Any]:
    """Build the candidate profile section from a resume row.

    When the resume row carries a Ticket-009 rich profile in
    ``analysis_json``, we aggregate skills from every category
    (skills, technologies, programming_languages, frameworks, cloud,
    databases, tools) into a single normalized skill list used by the
    matching engine. The legacy DB columns remain as a fallback when
    no rich profile is present.
    """
    rich = resume.analysis_json if isinstance(resume.analysis_json, dict) else {}

    aggregated_skills = _aggregate_skills(
        [
            rich.get("skills") or [],
            rich.get("technologies") or [],
            rich.get("programming_languages") or [],
            rich.get("frameworks") or [],
            rich.get("cloud") or [],
            rich.get("databases") or [],
            rich.get("tools") or [],
            list(resume.skills or []),
            list(resume.technologies or []),
        ]
    )

    return {
        "name": (rich.get("name") or resume.name or ""),
        "email": (rich.get("email") or resume.email or ""),
        "phone": (rich.get("phone") or resume.phone or ""),
        "location": (rich.get("location") or resume.location or ""),
        "summary": (
            rich.get("professional_summary")
            or rich.get("summary")
            or resume.summary
            or ""
        ),
        "years_of_experience": (
            rich.get("years_of_experience") or ""
        ),
        "recommended_roles": list(rich.get("recommended_roles") or []),
        "skills": aggregated_skills,
        "technologies": list(
            rich.get("technologies") or resume.technologies or []
        ),
        "experience": list(resume.experience or []),
        "education": list(resume.education or []),
        "rich_profile": rich,
    }


def _format_skills_list(skills: List[str]) -> str:
    """Format a list of skills as a natural-language phrase.

    Preserves the original casing of each skill (no ``.title()``) so
    things like "FastAPI" render as "FastAPI". Uses a plain comma list
    without the Oxford comma to match the wording in Ticket-010.
    """
    if not skills:
        return ""
    if len(skills) == 1:
        return skills[0]
    if len(skills) == 2:
        return f"{skills[0]} and {skills[1]}"
    return ", ".join(skills[:-1]) + f" and {skills[-1]}"


def _build_reason(overlap: List[str], company: Dict[str, Any]) -> str:
    """Build a personalized 'why it matches' reason from overlapping skills.

    The text is deterministic — no LLM call. The phrasing surfaces
    actual overlapping technologies by name so reviewers can see why
    the orchestrator ranked this company highly.
    """
    if not overlap:
        return (
            f"{company['name']} doesn't directly require the skills listed "
            "on your resume, but their broader stack and hiring signals "
            "are adjacent to your background — worth a closer look."
        )

    visible = overlap[:4]
    skills_text = _format_skills_list(visible)
    if len(overlap) > 4:
        skills_text += " and more"

    return (
        f"Matched because your experience with {skills_text} aligns "
        f"with {company['name']}'s preferred engineering stack."
    )


def _score_company(company: Dict[str, Any], candidate_skills: List[str]) -> Dict[str, Any]:
    """Score one company against the candidate on a true 0-100 scale.

    Replaces the previous ``min(98, 70 + overlap_count * 6)`` formula, which
    collapsed every company onto a narrow band:

    * it was floored at 70, so nothing could ever score below it;
    * it could only ever emit six values (70/76/82/88/94/98);
    * it counted raw overlap only, so matching 3 of 3 required skills scored
      the same as matching 3 of 20; and
    * discovered companies carry 1-2 generic skill tags (usually just "AI"),
      so the overlap was nearly always 0 and virtually every company landed
      on exactly 70.

    Scoring is a weighted blend of signals already present on the company
    record. Every input is read from data, so the function stays pure and
    deterministic: the same resume and company always yield the same score,
    and ranking is stable across calls.

        skill fit           0-50   how much of their stack the candidate has
        hiring activity     0-18   are they actually recruiting
        funding stage       0-14   stage-typical hiring appetite
        funding momentum    0-8    size of the round = budget to hire
        work mode           0-5    remote removes a relocation barrier
        seniority alignment 0-5    candidate experience vs the level they want

    Unknown signals score a neutral middle value rather than zero, so a
    sparsely-enriched record settles mid-table instead of being pushed to the
    bottom by missing data alone.

    The returned shape is unchanged — ``{"company", "score", "overlap"}`` —
    and ``overlap`` still contains only the company's own lowercased skill
    tokens, which callers rely on to map back to original casing.
    """
    company_skills = [s.lower() for s in company.get("skills", []) if s]
    overlap = _matched_company_skills(company_skills, candidate_skills)

    score = (
        _skill_fit_points(company_skills, overlap)
        + _hiring_points(company)
        + _funding_stage_points(company)
        + _funding_momentum_points(company)
        + _work_mode_points(company)
        + _seniority_points(company, candidate_skills)
    )

    return {
        "company": company,
        "score": max(0, min(100, int(round(score)))),
        "overlap": overlap,
    }


# ─── Match-scoring signals ──────────────────────────────────────────────
#
# All helpers below are pure functions of their inputs — no clocks, no
# randomness, no I/O — so scores are reproducible for a given resume.

# Maps a raw skill token to the broader concepts it demonstrates, applied to
# BOTH the company and the candidate before comparing. Discovery tags
# companies with umbrella terms like "AI", which a literal set intersection
# would never match against a resume listing "PyTorch" or "NLP" — that
# mismatch is a large part of why overlap was so often empty.
_SKILL_CONCEPTS = {
    "ai": {"ai"},
    "artificial intelligence": {"ai"},
    "machine learning": {"ai", "ml"},
    "ml": {"ai", "ml"},
    "deep learning": {"ai", "ml", "deep learning"},
    "neural networks": {"ai", "ml", "deep learning"},
    "pytorch": {"ai", "ml", "deep learning", "pytorch"},
    "tensorflow": {"ai", "ml", "deep learning", "tensorflow"},
    "keras": {"ai", "ml", "deep learning"},
    "jax": {"ai", "ml", "deep learning"},
    "scikit-learn": {"ai", "ml"},
    "pandas": {"ai", "ml", "data"},
    "numpy": {"ai", "ml", "data"},
    "nlp": {"ai", "nlp"},
    "natural language processing": {"ai", "nlp"},
    "llm": {"ai", "nlp", "llm"},
    "llms": {"ai", "nlp", "llm"},
    "large language models": {"ai", "nlp", "llm"},
    "generative ai": {"ai", "llm"},
    "transformers": {"ai", "nlp", "llm"},
    "rag": {"ai", "nlp", "llm"},
    "computer vision": {"ai", "cv"},
    "cv": {"ai", "cv"},
    "image processing": {"ai", "cv"},
    "opencv": {"ai", "cv"},
    "mlops": {"ai", "ml", "mlops", "infrastructure"},
    "data science": {"ai", "ml", "data"},
    "data engineering": {"data", "infrastructure"},
    "recommendation systems": {"ai", "ml"},
    "edge computing": {"infrastructure", "distributed systems"},
    "distributed systems": {"infrastructure", "distributed systems"},
    "microservices": {"infrastructure", "distributed systems"},
    "kubernetes": {"infrastructure", "devops"},
    "docker": {"infrastructure", "devops"},
    "terraform": {"infrastructure", "devops"},
    "aws": {"infrastructure", "cloud"},
    "gcp": {"infrastructure", "cloud"},
    "azure": {"infrastructure", "cloud"},
}


def _concepts_for(skill: str) -> set:
    """Expand one skill token into the concepts it demonstrates.

    Unknown tokens map to themselves, so exact matching still works for
    anything outside the table above.
    """
    key = (skill or "").strip().lower()
    if not key:
        return set()
    return _SKILL_CONCEPTS.get(key, {key})


def _matched_company_skills(
    company_skills: List[str], candidate_skills: List[str]
) -> List[str]:
    """Return the company skills the candidate can satisfy.

    Entries are always the COMPANY's own lowercased tokens, never the
    candidate's or an expanded concept name. Callers map these back through
    ``{s.lower(): s for s in company["skills"]}`` to recover original casing,
    which would raise ``KeyError`` on any other value.
    """
    candidate_concepts = set()
    for skill in candidate_skills or []:
        candidate_concepts |= _concepts_for(skill)

    if not candidate_concepts:
        return []

    return sorted(
        {
            skill
            for skill in company_skills
            if _concepts_for(skill) & candidate_concepts
        }
    )


# A candidate matching this many of a company's skills is treated as having
# full depth. Prevents companies that list many skills from being unreachable
# and companies that list one from being trivially maxed.
_SKILL_DEPTH_TARGET = 4


def _skill_fit_points(company_skills: List[str], overlap: List[str]) -> float:
    """Skill component, 0-50.

    Blends coverage (share of their stack the candidate has) with depth
    (absolute number of matching skills) so that 3-of-3 outranks 3-of-20 while
    a broad match still counts for something.
    """
    unique_skills = set(company_skills)
    if not unique_skills:
        # Nothing listed to judge against — neutral rather than zero, so an
        # unenriched record is not punished for missing data.
        return 20.0

    matched = len(overlap)
    coverage = matched / len(unique_skills)
    depth = matched / min(_SKILL_DEPTH_TARGET, len(unique_skills))
    return 50.0 * (0.6 * coverage + 0.4 * min(1.0, depth))


def _hiring_points(company: Dict[str, Any]) -> float:
    """Hiring component, 0-18.

    Prefers the enriched ``hiring_status_detailed`` field and falls back to
    the funding round, which is the same heuristic the companies route uses
    to display a hiring badge — so score and badge agree.
    """
    status = (company.get("hiring_status_detailed") or "").strip().lower()
    if status == "actively_hiring":
        return 18.0
    if status == "hiring":
        return 13.0
    if status == "not_hiring":
        return 2.0

    stage = (company.get("funding_round") or "").lower()
    if any(s in stage for s in ("series b", "series c", "series d", "series e", "series f")):
        return 14.0
    if "series a" in stage:
        return 11.0
    return 8.0  # unknown — neutral


def _funding_stage_points(company: Dict[str, Any]) -> float:
    """Funding-stage component, 0-14.

    Early-growth companies hire hardest; pre-seed is riskier and late stage
    is slower-moving, so both sit below the Series A/B peak.
    """
    stage = (company.get("funding_round") or "").lower()
    if "pre-seed" in stage or "preseed" in stage:
        return 9.0
    if "seed" in stage:
        return 12.0
    if "series a" in stage:
        return 14.0
    if "series b" in stage:
        return 12.0
    if "series c" in stage:
        return 9.0
    if any(s in stage for s in ("series d", "series e", "series f", "pre-ipo", "ipo")):
        return 6.0
    return 7.0  # unknown — neutral


def _funding_momentum_points(company: Dict[str, Any]) -> float:
    """Round-size component, 0-8. A larger raise means more hiring budget."""
    millions = _funding_millions(company.get("funding_amount", ""))
    if millions is None:
        return 3.0  # unknown — neutral
    if millions >= 100:
        return 8.0
    if millions >= 50:
        return 7.0
    if millions >= 20:
        return 6.0
    if millions >= 5:
        return 5.0
    if millions >= 1:
        return 4.0
    return 3.0


def _funding_millions(amount: str) -> Optional[float]:
    """Parse "$130.0M" / "$50B" / "$900K" into millions. None when unparseable."""
    text = (amount or "").strip().lower().replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*([bmk])?", text)
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    unit = match.group(2)
    if unit == "b":
        return value * 1000
    if unit == "k":
        return value / 1000
    return value


def _work_mode_points(company: Dict[str, Any]) -> float:
    """Work-mode component, 0-5. Remote removes a relocation barrier."""
    mode = (company.get("work_mode") or "").strip().lower()
    if mode == "remote":
        return 5.0
    if mode == "hybrid":
        return 3.0
    if mode == "onsite":
        return 1.0
    if company.get("remote_friendly") is True:
        return 5.0
    return 2.0  # unknown — neutral


def _seniority_points(company: Dict[str, Any], candidate_skills: List[str]) -> float:
    """Seniority component, 0-5.

    ``candidate_skills`` carries no experience data, so this rewards breadth
    of stack as a proxy for depth of experience. It stays deterministic and
    keeps a strong generalist ahead of a narrow profile at companies that
    named a senior preference.
    """
    level = (company.get("preferred_experience_level") or "").strip().lower()
    breadth = len({(s or "").strip().lower() for s in (candidate_skills or []) if s})

    if level in ("senior", "principal", "staff"):
        return 5.0 if breadth >= 8 else 2.0
    if level in ("junior", "entry level", "entry-level", "new grad", "intern"):
        return 5.0 if breadth <= 10 else 3.0
    if level == "mid":
        return 5.0 if breadth >= 5 else 3.0
    return 3.0  # unknown — neutral



def _select_top_matches(
    companies: List[Dict[str, Any]], candidate_skills: List[str]
) -> List[Dict[str, Any]]:
    """Score, sort, and return the top 3 companies for the candidate."""
    scored = [_score_company(c, candidate_skills) for c in companies]
    # Stable ordering: highest score first, then alphabetical for deterministic ties.
    scored.sort(key=lambda x: (-x["score"], x["company"]["name"]))
    top = scored[:3]

    results: List[Dict[str, Any]] = []
    for item in top:
        result = dict(item["company"])  # all seed fields
        result["score"] = item["score"]
        result["reason"] = _build_reason(item["overlap"], item["company"])
        results.append(result)
    return results


def run_weekly_report(db: Session, user_id: str) -> Dict[str, Any]:
    """Run the weekly career intelligence report workflow.

    Ticket-014 refactor: the orchestrator now exposes six explicit
    stages of a Career Intelligence Agent. Stages are synchronous;
    no LangGraph, no async workers.

        Stage 1 - Resume Intelligence
        Stage 2 - Market Intelligence
        Stage 3 - Company Intelligence
        Stage 4 - Career Intelligence
        Stage 5 - Opportunity Ranking
        Stage 6 - Report Assembly

    Stage 1 is user-scoped; stages 2-6 are pure functions of
    ``(candidate, companies)``, so scoping the resume lookup is
    sufficient to make the whole report user-specific. The company set
    itself stays global and identical for every user.

    Args:
        db: SQLAlchemy session.
        user_id: Owner of the report. Only this user's resume is read.

    Returns:
        Dictionary with either:
        - {summary, candidate, generated_at, companies_found,
           top_matches, cover_letter, market_summary,
           industry_breakdown, career_intelligence,
           technology_breakdown, top_strengths, top_skill_gaps}
        - {requires_resume: True, message}
    """
    from app.services.user_scope import get_user_resume

    # ---------- Stage 1: Resume Intelligence ----------
    _log_stage("Reading Resume", 0.3)
    latest_resume: Optional[Resume] = get_user_resume(db, user_id)

    if latest_resume is None:
        return {
            "requires_resume": True,
            "message": "Please upload your resume first.",
        }

    _log_stage("Understanding Candidate Profile", 0.3)
    candidate = _build_candidate(latest_resume)

    # ---------- Stage 2: Market Intelligence ----------
    _log_stage("Discovering High-Growth AI Companies", 0.4)
    companies = _load_companies()
    market = market_intelligence(companies)
    market_summary = market["market_summary"]
    industry_breakdown = market["industry_breakdown"]

    # ---------- Stage 3: Company Intelligence ----------
    _log_stage("Matching Skills", 0.3)
    top_matches = _select_top_matches(companies, candidate["skills"])

    # ---------- Stage 4: Career Intelligence ----------
    _log_stage("Ranking Opportunities", 0.3)
    career = career_intelligence(candidate, companies, top_matches)
    career_intelligence_block = career["career_intelligence"]
    technology_breakdown = career["technology_breakdown"]
    top_strengths = career["top_strengths"]
    top_skill_gaps = career["top_skill_gaps"]

    # ---------- Stage 5: Opportunity Ranking (already done in Stage 3) ----------
    # top_matches is already sorted by score desc + name asc.

    # ---------- Stage 6: Report Assembly ----------
    _log_stage("Generating Cover Letter", 0.4)
    cover_letter = None
    if top_matches:
        cover_letter = generate_cover_letter(candidate, top_matches[0])

    _log_stage("Preparing Weekly Career Report", 0.4)

    name = candidate.get("name") or ""
    if name:
        summary = f"Weekly Career Intelligence Report for {name}"
    else:
        summary = "Weekly Career Intelligence Report"

    return {
        "summary": summary,
        "candidate": candidate,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "companies_found": len(companies),
        "top_matches": top_matches,
        "cover_letter": cover_letter,
        # ----- Ticket-014 new intelligence fields -----
        "market_summary": market_summary,
        "industry_breakdown": industry_breakdown,
        "career_intelligence": career_intelligence_block,
        "technology_breakdown": technology_breakdown,
        "top_strengths": top_strengths,
        "top_skill_gaps": top_skill_gaps,
    }