"""Orchestrator service - coordinates the weekly career report workflow.

This is the foundation module that all future AI services plug into.
Currently produces personalized reports from real-world AI startup
discovery (Tavily + Firecrawl + OpenAI), with a local cache and a
Demo Data fallback when discovery is unavailable.
"""

import json
import logging
import os
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
        # Preserve Career Intelligence metadata if present.
        for key in ("recommendations_resume_id",
                     "recommendations_generated_at"):
            if key in existing and key not in envelope:
                envelope[key] = existing[key]
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
    """Run the live discovery pipeline. Raises on any failure."""
    from app.services.discovery_service import discover_companies_from_web

    companies = discover_companies_from_web()
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
    if cached is not None:
        # Existing cache is authoritative. Return its companies verbatim,
        # regardless of data_source. The caller can inspect metadata to
        # decide whether to surface "seed fallback" UI hints.
        return cached["companies"] if isinstance(cached, dict) else cached

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
    """Score one company against the candidate's skills.

    Score formula: 70 + (overlap_count * 6), capped at 98.
    Lower bound is 70 (matches the ticket's required range).
    """
    company_skills = {s.lower() for s in company.get("skills", [])}
    candidate_set = {s.lower() for s in candidate_skills}
    overlap = sorted(company_skills & candidate_set)
    score = min(98, 70 + len(overlap) * 6)
    return {"company": company, "score": score, "overlap": overlap}


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


def run_weekly_report(db: Session) -> Dict[str, Any]:
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

    Args:
        db: SQLAlchemy session.

    Returns:
        Dictionary with either:
        - {summary, candidate, generated_at, companies_found,
           top_matches, cover_letter, market_summary,
           industry_breakdown, career_intelligence,
           technology_breakdown, top_strengths, top_skill_gaps}
        - {requires_resume: True, message}
    """
    # ---------- Stage 1: Resume Intelligence ----------
    _log_stage("Reading Resume", 0.3)
    latest_resume: Optional[Resume] = (
        db.query(Resume).order_by(Resume.parsed_at.desc()).first()
    )

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