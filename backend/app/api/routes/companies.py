"""
Company endpoints
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.resume import Resume
from app.services.orchestrator import (
    _build_candidate,
    _build_reason,
    _load_companies,
    _score_company,
)

router = APIRouter()


class DiscoverRequest(BaseModel):
    """Request body for company discovery."""
    force_refresh: bool = Field(default=False, description="Force cache refresh and run live discovery")


class DiscoverResponse(BaseModel):
    """Response from company discovery."""
    companies: List[Dict[str, Any]]
    total: int
    cache_metadata: Dict[str, Any]
    discovery_stats: Dict[str, Any]
    cache_health: Optional[Dict[str, Any]] = None


class MatchRequest(BaseModel):
    """Request body for company matching."""
    skills: List[str] = Field(..., description="Candidate skills list")
    experience_years: Optional[int] = Field(None, description="Years of experience")
    primary_skills: Optional[List[str]] = Field(None, description="Primary skills to weight higher")
    secondary_skills: Optional[List[str]] = Field(None, description="Secondary skills")
    limit: Optional[int] = Field(default=10, description="Maximum number of matches to return")


class MatchResponse(BaseModel):
    """Response from company matching."""
    matches: List[Dict[str, Any]]
    total_companies: int
    candidate_profile: Dict[str, Any]
    match_metadata: Dict[str, Any]


@router.post("/discover", response_model=DiscoverResponse)
async def discover_companies(payload: DiscoverRequest):
    """
    Discover newly funded companies.

    Triggers live company discovery via Tavily + Firecrawl + OpenAI.
    Respects existing cache unless force_refresh is True.
    Returns discovered companies with metadata and statistics.
    """
    from app.services.orchestrator import (
        _read_cache,
        _run_discovery,
        _write_cache,
        _load_seed_companies,
        invalidate_cache,
        get_cache_stats,
    )
    import time

    start_time = time.time()
    companies: List[Dict[str, Any]] = []
    cache_hit = False
    discovery_method = "cache"
    cache_metadata = {}

    if payload.force_refresh:
        invalidate_cache()

    cached = _read_cache()
    if cached is not None:
        companies = cached["companies"] if isinstance(cached, dict) else cached
        cache_hit = True
        discovery_method = "cache"
        cache_metadata = cached if isinstance(cached, dict) else {}

    if not companies:
        try:
            companies = _run_discovery()
            cache_metadata = _write_cache(companies)
            discovery_method = "live"
        except Exception as exc:
            companies = _load_seed_companies()
            cache_metadata = _write_cache(companies)
            discovery_method = "seed_fallback"

    duration = time.time() - start_time
    cache_stats = get_cache_stats()

    return DiscoverResponse(
        companies=companies,
        total=len(companies),
        cache_metadata={
            "cache_hit": cache_hit,
            "discovery_method": discovery_method,
            "duration_seconds": round(duration, 2),
            **cache_metadata,
        },
        discovery_stats={
            "total_companies": len(companies),
            "industries": len(set(c.get("industry", "") for c in companies)),
            "funding_stages": len(set(c.get("funding_round", "") for c in companies)),
        },
        cache_health=cache_stats,
    )


@router.post("/match", response_model=MatchResponse)
async def match_companies(payload: MatchRequest, db: Session = Depends(get_db)):
    """
    Match companies with candidate profile.

    Calculates matching scores using enhanced weighted scoring algorithm
    considering skills, experience, education, and projects. Returns ranked
    companies with detailed match information.
    """
    from app.services.matching_engine import EnhancedMatchingEngine
    
    companies = _load_companies()
    
    # Build candidate profile from request
    candidate_profile = {
        "skills": payload.skills,
        "experience_years": payload.experience_years,
        "primary_skills": payload.primary_skills or [],
        "secondary_skills": payload.secondary_skills or [],
        "years_of_experience": f"{payload.experience_years}+ years" if payload.experience_years else "",
    }
    
    # Add experience and education from latest resume if available
    latest_resume = db.query(Resume).order_by(Resume.parsed_at.desc()).first()
    if latest_resume:
        candidate_profile["experience"] = latest_resume.experience or []
        candidate_profile["education"] = latest_resume.education or []
        candidate_profile["projects"] = latest_resume.projects or []
        if not candidate_profile["years_of_experience"]:
            rich = latest_resume.analysis_json or {}
            candidate_profile["years_of_experience"] = rich.get("years_of_experience", "")
    
    # Score all companies using enhanced engine
    scored = []
    for company in companies:
        result = EnhancedMatchingEngine.calculate_match(company, candidate_profile)
        scored.append({
            "company": company,
            "result": result,
        })
    
    # Sort by overall score descending
    scored.sort(key=lambda x: (-x["result"]["overall_score"], x["company"]["name"]))
    
    # Take top matches
    limit = min(payload.limit, len(scored))
    top_matches = scored[:limit]
    
    # Build detailed match responses
    matches = []
    for item in top_matches:
        company = item["company"]
        result = item["result"]
        
        # Restore original casing of skills
        original_by_lower = {s.lower(): s for s in company.get("skills", [])}
        matching_skills = [original_by_lower[s] for s in result["overlap"]]
        missing_skills = [original_by_lower[s] for s in result["missing_skills"]]
        
        matches.append({
            "company": company,
            "score": result["overall_score"],
            "overlap_count": result["overlap_count"],
            "matching_skills": matching_skills,
            "missing_skills": missing_skills,
            "reason": _build_reason(result["overlap"], company),
            "confidence": _calculate_confidence(result["overall_score"], result["overlap_count"]),
            "recommendations": _build_recommendations(result["overlap"], missing_skills),
            "score_breakdown": {
                "overall_score": result["overall_score"],
                "skill_score": result["skill_score"],
                "experience_score": result["experience_score"],
                "education_score": result["education_score"],
                "project_score": result["project_score"],
                "recommendation_score": result["recommendation_score"],
            },
            "strengths": result["strengths"],
            "gaps": result["gaps"],
        })
    
    return MatchResponse(
        matches=matches,
        total_companies=len(companies),
        candidate_profile=candidate_profile,
        match_metadata={
            "companies_scored": len(scored),
            "matches_returned": len(matches),
            "highest_score": matches[0]["score"] if matches else 0,
            "lowest_score": matches[-1]["score"] if matches else 0,
            "scoring_method": "enhanced_weighted",
        },
    )


def _calculate_confidence(score: int, overlap_count: int) -> str:
    """Calculate confidence level based on score and overlap."""
    if score >= 90:
        return "high"
    if score >= 75:
        return "medium"
    return "low"


def _build_recommendations(overlap: List[str], missing_skills: List[str]) -> List[str]:
    """Build personalized recommendations based on match results."""
    recommendations = []
    
    if overlap:
        recommendations.append(f"Leverage your {len(overlap)} matching skills as competitive advantages")
    
    if missing_skills:
        if len(missing_skills) <= 3:
            skills_text = ", ".join(missing_skills[:3])
            recommendations.append(f"Consider building experience with: {skills_text}")
        else:
            recommendations.append(f"Focus on top 3 missing skills: {', '.join(missing_skills[:3])}")
    
    if not overlap:
        recommendations.append("Consider whether the role aligns with your career trajectory despite skill gaps")
    
    return recommendations


def _parse_funding_millions(amount: str) -> float:
    """Parse funding string to millions for sorting."""
    if not amount:
        return 0.0
    import re
    match = re.search(r"\$?(\d+(?:\.\d+)?)\s*([KMB])?", str(amount), re.IGNORECASE)
    if not match:
        return 0.0
    num = float(match.group(1))
    unit = (match.group(2) or "M").upper()
    unit_multipliers = {"K": 0.001, "M": 1.0, "B": 1000.0}
    return num * unit_multipliers.get(unit, 1.0)


def _parse_company_size_sort(size_str: str) -> int:
    """Parse company size string to numeric value for sorting."""
    if not size_str:
        return 0
    if "500+" in size_str:
        return 500
    if "201-500" in size_str:
        return 200
    if "51-200" in size_str:
        return 50
    if "11-50" in size_str:
        return 10
    if "1-10" in size_str:
        return 1
    return 0


def _find_company(company_name: str):
    """Find a company by name (case-insensitive) in the active company set."""
    companies = _load_companies()
    target = company_name.strip().lower()
    for entry in companies:
        if entry.get("name", "").lower() == target:
            return entry
    return None


def _build_match(company: dict, candidate: dict) -> dict:
    """Reuse orchestrator scoring helpers to build the match payload."""
    result = _score_company(company, candidate["skills"])

    # Orchestrator compares skills case-insensitively, so restore the
    # original casing from the seed (e.g. "fastapi" -> "FastAPI").
    original_by_lower = {s.lower(): s for s in company.get("skills", [])}
    matching_skills = [original_by_lower[s] for s in result["overlap"]]

    company_skills = {s.lower() for s in company.get("skills", [])}
    candidate_set = {s.lower() for s in (candidate.get("skills") or [])}
    missing_lowercase = sorted(company_skills - candidate_set)[:4]
    missing_skills = [original_by_lower[s] for s in missing_lowercase]

    return {
        "score": result["score"],
        "matching_skills": matching_skills,
        "missing_skills": missing_skills,
        "reason": _build_reason(result["overlap"], company),
    }


def _company_id(company: dict) -> str:
    """Derive a stable ID from the company name."""
    name = (company.get("name") or "").strip()
    return name.lower().replace(" ", "-").replace(".", "").replace(",", "")


def _infer_company_size(company: dict) -> str:
    """Heuristic mapping from funding round to a rough headcount band."""
    stage = (company.get("funding_round") or "").lower()
    if "seed" in stage:
        return "1-10"
    if "series a" in stage:
        return "11-50"
    if "series b" in stage:
        return "51-200"
    if "series c" in stage:
        return "201-500"
    if any(s in stage for s in ["series d", "series e", "series f"]):
        return "500+"
    return ""


def _infer_hiring_status(company: dict) -> str:
    """Heuristic: later-stage funded companies are typically hiring more."""
    stage = (company.get("funding_round") or "").lower()
    if any(s in stage for s in ["series b", "series c", "series d", "series e", "series f"]):
        return "Actively hiring"
    if "series a" in stage:
        return "Hiring"
    return "Selective hiring"


# ---------- Deterministic match explanation helpers (Ticket-013) ----------

# Categorizations used purely for phrasing. Mirrors the AI prompt's
# intent; safe to keep in sync with Ticket-009 expectations.
_PROGRAMMING_LANGUAGES = {
    "Python", "TypeScript", "JavaScript", "Go", "Rust", "Java",
    "C++", "C#", "Ruby", "PHP", "Swift", "Kotlin", "Mojo", "CUDA",
}
_DATABASES = {
    "PostgreSQL", "MongoDB", "Redis", "MySQL", "Elasticsearch",
}
_CLOUD = {"AWS", "GCP", "Azure"}
_TOOLS = {"Docker", "Kubernetes", "Git", "Linux", "Terraform"}


def _strength_statement(skill: str) -> str:
    """Render a single skill as a personalized strength statement."""
    if skill in _PROGRAMMING_LANGUAGES:
        return f"Strong {skill} background"
    return f"{skill} experience"


def _learning_path(skill: str) -> str:
    """Suggest a learning path phrasing for a single missing skill."""
    mapping = {
        "Docker": "Containerization with Docker",
        "Kubernetes": "Container orchestration with Kubernetes",
        "AWS": "Cloud infrastructure on AWS",
        "GCP": "Cloud infrastructure on GCP",
        "Azure": "Cloud infrastructure on Azure",
        "PyTorch": "Deep learning with PyTorch",
        "TensorFlow": "Deep learning with TensorFlow",
        "Rust": "Systems programming with Rust",
        "Go": "Backend services with Go",
        "Redis": "In-memory data stores (Redis)",
        "PostgreSQL": "Relational databases (PostgreSQL)",
        "MongoDB": "Document databases (MongoDB)",
        "NLP": "Natural language processing",
        "Distributed Systems": "Distributed systems design",
        "CUDA": "GPU computing (CUDA)",
        "Mojo": "Performance-oriented languages (Mojo)",
        "Compiler": "Compiler design and implementation",
        "MLIR": "Compiler infrastructure (MLIR)",
    }
    return mapping.get(skill, f"Build experience with {skill}")


def _build_matching_summary(
    company: dict,
    overlap: list,
    missing_skills: list,
    score: int,
) -> str:
    """One-paragraph summary of overall fit, tuned to the score band."""
    name = company.get("name", "This company")
    overlap_preview = ", ".join(overlap[:3]) if overlap else "no overlapping skills"

    if score >= 92:
        return (
            f"{name} is an excellent match for your background. "
            f"You bring {len(overlap)} of their core technologies "
            f"({overlap_preview}), positioning you as a strong candidate."
        )
    if score >= 82:
        return (
            f"{name} is a strong fit. "
            f"You bring {len(overlap)} directly relevant skills "
            f"({overlap_preview}) that align with their engineering priorities."
        )
    if score >= 70:
        return (
            f"{name} is a moderate fit. "
            f"Your {len(overlap)} overlapping skill(s) provide a foundation, "
            f"though they prioritize {len(missing_skills)} technology "
            f"area(s) outside your current profile."
        )
    return (
        f"{name} doesn't directly match your current profile. "
        f"Consider whether the role and mission align with your longer-term career goals."
    )


def _build_matching_strengths(overlap: list, candidate: dict) -> list:
    """Render each overlapping skill as a personalized strength statement."""
    rich = candidate.get("rich_profile") or {}
    roles = rich.get("recommended_roles") or []
    strengths = [_strength_statement(skill) for skill in overlap[:5]]
    if roles and len(strengths) < 5:
        strengths.append(f"{roles[0]} experience")
    return strengths


def _build_recommended_learning(missing_skills: list) -> list:
    """For each missing skill, return a deterministic learning path."""
    return [_learning_path(skill) for skill in missing_skills[:4]]


def _build_career_alignment(company: dict, candidate: dict) -> str:
    """One-paragraph alignment statement tailored to the candidate's role focus."""
    rich = candidate.get("rich_profile") or {}
    roles = rich.get("recommended_roles") or []
    role_text = roles[0] if roles else "your target"
    industry = company.get("industry") or "their sector"
    tagline = (company.get("tagline") or "").strip()

    tagline_clause = (
        f" Their mission — {tagline} — fits naturally with someone building depth in your domain."
        if tagline
        else ""
    )

    return (
        f"This opportunity aligns with your current {role_text} trajectory "
        f"and provides strong exposure to {industry}.{tagline_clause} "
        f"{company.get('name', 'This company')} is a natural next step "
        f"for someone building momentum in your area."
    )


@router.get("")
async def list_companies(
    db: Session = Depends(get_db),
    industry: Optional[str] = Query(None, description="Filter by industry"),
    location: Optional[str] = Query(None, description="Filter by location"),
    funding_stage: Optional[str] = Query(None, description="Filter by funding stage"),
    hiring_status: Optional[str] = Query(None, description="Filter by hiring status"),
    min_score: Optional[int] = Query(None, ge=0, le=100, description="Minimum match score"),
    technology: Optional[str] = Query(None, description="Filter by technology skill"),
    search: Optional[str] = Query(None, description="Search in name, tagline, or industry"),
    sort_by: Optional[str] = Query("match_score", description="Sort field"),
    sort_order: Optional[str] = Query("desc", description="Sort order (asc/desc)"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
):
    """Return companies with filtering, sorting, and pagination against the latest resume.

    Supports filtering by industry, location, funding stage, hiring status,
    minimum score, technology, and text search. Supports sorting by match score,
    funding amount, company size, alphabetical, and newest. Supports pagination
    with page-based navigation.
    """
    # Load companies once
    companies = _load_companies()
    
    # Pre-compute company metadata for performance
    company_metadata = {}
    for company in companies:
        company_metadata[company.get("name", "")] = {
            "size": _infer_company_size(company),
            "hiring": _infer_hiring_status(company),
            "funding_millions": _parse_funding_millions(company.get("funding_amount", "")),
            "size_sort": _parse_company_size_sort(_infer_company_size(company)),
        }
    
    latest_resume = (
        db.query(Resume).order_by(Resume.parsed_at.desc()).first()
    )

    has_resume = latest_resume is not None
    candidate = _build_candidate(latest_resume) if has_resume else None

    # Apply filters
    filtered = companies
    if industry:
        filtered = [c for c in filtered if c.get("industry", "").lower() == industry.lower()]
    if location:
        filtered = [c for c in filtered if location.lower() in c.get("headquarters", "").lower()]
    if funding_stage:
        filtered = [c for c in filtered if funding_stage.lower() in c.get("funding_round", "").lower()]
    if hiring_status:
        filtered = [
            c for c in filtered 
            if hiring_status.lower() == company_metadata[c.get("name", "")]["hiring"].lower()
        ]
    if technology:
        filtered = [c for c in filtered if technology.lower() in {s.lower() for s in c.get("skills", [])}]
    if search:
        search_lower = search.lower()
        filtered = [
            c for c in filtered
            if search_lower in c.get("name", "").lower()
            or search_lower in c.get("tagline", "").lower()
            or search_lower in c.get("industry", "").lower()
        ]

    # Score companies if candidate exists
    scored = []
    for company in filtered:
        meta = company_metadata.get(company.get("name", ""), {})
        
        item = {
            "id": _company_id(company),
            "name": company.get("name", ""),
            "logo": None,
            "industry": company.get("industry", ""),
            "headquarters": company.get("headquarters", ""),
            "funding_stage": company.get("funding_round", ""),
            "funding_amount": company.get("funding_amount", ""),
            "founded_year": company.get("founded", ""),
            "company_size": meta.get("size", ""),
            "hiring_status": meta.get("hiring", ""),
            "match_score": None,
            "matching_skills": [],
            "short_description": company.get("tagline", ""),
            "why_match": "Upload a resume to see your personalized match.",
        }

        if candidate:
            result = _score_company(company, candidate["skills"])
            # Apply min_score filter
            if min_score is not None and result["score"] < min_score:
                continue
            # Restore original casing of overlapping skills
            original_by_lower = {
                s.lower(): s for s in company.get("skills", [])
            }
            matching_skills = [
                original_by_lower[s] for s in result["overlap"]
            ][:6]
            item["match_score"] = result["score"]
            item["matching_skills"] = matching_skills
            item["why_match"] = _build_reason(result["overlap"], company)

        scored.append(item)

    # Apply sorting using pre-computed values
    valid_sort_fields = {
        "match_score": lambda x: x.get("match_score", 0),
        "funding_amount": lambda x: company_metadata.get(x.get("name", ""), {}).get("funding_millions", 0),
        "company_size": lambda x: company_metadata.get(x.get("name", ""), {}).get("size_sort", 0),
        "alphabetical": lambda x: x.get("name", "").lower(),
        "newest": lambda x: int(x.get("founded_year", "0")),
    }
    
    if sort_by in valid_sort_fields:
        reverse = sort_order.lower() == "desc"
        scored.sort(key=valid_sort_fields[sort_by], reverse=reverse)
    else:
        # Default: sort by match score descending, then alphabetical
        scored.sort(key=lambda x: (-x.get("match_score", 0), x.get("name", "").lower()))

    # Apply pagination
    total = len(scored)
    offset = (page - 1) * limit
    paginated = scored[offset:offset + limit]

    return {
        "companies": paginated,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit,
        "has_next": offset + limit < total,
        "has_previous": page > 1,
        "has_resume": has_resume,
    }


@router.get("/{company_name}")
async def get_company(company_name: str, db: Session = Depends(get_db)):
    """Return company profile + deterministic match against the latest resume.

    Reuses the seed dataset and orchestrator scoring helpers — no OpenAI
    call. If no resume has been uploaded, the match section degrades to
    score=0 with a helpful message. Ticket-013 adds five deterministic
    explanation fields at the top level for the explainable AI report.
    """
    company = _find_company(company_name)
    if company is None:
        raise HTTPException(
            status_code=404,
            detail=f"Company '{company_name}' not found",
        )

    latest_resume = (
        db.query(Resume).order_by(Resume.parsed_at.desc()).first()
    )

    if latest_resume is None:
        company_skills = company.get("skills", [])
        return {
            "company": company,
            "match": {
                "score": 0,
                "matching_skills": [],
                "missing_skills": company_skills[:4],
                "reason": (
                    "Upload your resume to see your personalized match analysis."
                ),
            },
            "matching_summary": None,
            "matching_strengths": [],
            "missing_skills": company_skills[:4],
            "recommended_learning": [],
            "career_alignment": None,
        }

    candidate = _build_candidate(latest_resume)
    match = _build_match(company, candidate)
    overlap = match["matching_skills"]
    missing = match["missing_skills"]
    score = match["score"]

    return {
        "company": company,
        "match": match,
        "matching_summary": _build_matching_summary(company, overlap, missing, score),
        "matching_strengths": _build_matching_strengths(overlap, candidate),
        "missing_skills": missing,
        "recommended_learning": _build_recommended_learning(missing),
        "career_alignment": _build_career_alignment(company, candidate),
    }