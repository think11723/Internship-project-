"""Sprint 5 — Personalised Application Strategy layer.

Pure-deterministic layer that turns (company + resume + enrichment)
into a structured recommendation telling the candidate HOW TO APPLY,
not just WHETHER to apply. This is the second half of the original
requirement: "propose YOUR WAY IN."

Designed as an ADDITIVE service. Does not touch discovery, extraction,
or enrichment. Called from ``career_intelligence.generate_recommendation``
which merges the returned fields into the existing recommendation dict.

Every recommendation is derived from real inputs. If a field cannot be
derived (missing data), the field is either omitted or set to a clear
"Unknown" marker — never fabricated.
"""

from typing import Any, Dict, List, Optional


# ─── Helpers ───────────────────────────────────────────────────────────────

def _candidate_skill_set(resume: Optional[Dict[str, Any]]) -> set:
    """Normalise every skill the candidate has into a lowercase set."""
    if not resume:
        return set()
    out: set = set()
    for field in (
        "skills",
        "technologies",
        "programming_languages",
        "frameworks",
        "cloud",
        "databases",
        "tools",
    ):
        for s in (resume.get(field) or []):
            v = (s or "").strip().lower()
            if v:
                out.add(v)
    return out


def _company_skill_set(company: Dict[str, Any]) -> set:
    """Normalise every skill the company mentions into a lowercase set.

    Sprint 6: when the company carries real-job intelligence (from the
    careers-page scrape), real-job skills take precedence — they are
    what the candidate actually needs to apply, not the marketing
    tech stack.
    """
    out: set = set()
    for s in (company.get("skills") or []):
        v = (s or "").strip().lower()
        if v:
            out.add(v)
    enrichment = company.get("enrichment") or {}
    for s in (enrichment.get("tech_stack") or []):
        v = (s or "").strip().lower()
        if v:
            out.add(v)

    # Sprint 6: fold in real-job required + nice-to-have skills.
    ji = company.get("job_intelligence") or {}
    real_jobs = ji.get("jobs") or []
    if real_jobs:
        from app.services.job_intelligence import (
            derive_required_skills_from_jobs,
        )
        req, nice = derive_required_skills_from_jobs(real_jobs)
        for s in req + nice:
            v = (s or "").strip().lower()
            if v:
                out.add(v)

    return out


def _star_rating(overall_fit: int) -> str:
    """Convert overall_fit (0..100) to a 5-star string."""
    if overall_fit >= 80:
        return "★★★★★"
    if overall_fit >= 65:
        return "★★★★"
    if overall_fit >= 50:
        return "★★★"
    if overall_fit >= 35:
        return "★★"
    return "★"


def _fit_label(overall_fit: int) -> str:
    """Convert overall_fit to a short recommendation label."""
    if overall_fit >= 80:
        return "Strong Apply"
    if overall_fit >= 65:
        return "Good Fit"
    if overall_fit >= 50:
        return "Moderate Fit"
    if overall_fit >= 35:
        return "Stretch"
    if overall_fit > 0:
        return "Weak Match"
    return "Insufficient Data"


# ─── Industry-specific team mapping (deterministic) ───────────────────────

_TEAM_BY_INDUSTRY = (
    ("ai research", "Research / Alignment"),
    ("ai safety", "Research / Alignment"),
    ("foundation models", "Foundation Models"),
    ("ai infrastructure", "Platform / Infra"),
    ("ai silicon", "Systems / Hardware"),
    ("developer tools", "Product Engineering"),
    ("ai search", "Search / Ranking"),
    ("enterprise search", "Search Engineering"),
    ("generative ai", "Generative AI"),
    ("generative video", "Video / Multimodal"),
    ("computer vision", "Vision / Perception"),
    ("enterprise ai", "Applied AI"),
    ("mlops", "ML Platform"),
    ("vertical ai", "Domain Solutions"),
)


def _best_team_for_company(
    company: Dict[str, Any], enrichment: Dict[str, Any]
) -> str:
    """Determine the best-fit team for the candidate based on industry
    and the company's hiring departments."""
    industry = (company.get("industry") or "").lower()
    for key, team in _TEAM_BY_INDUSTRY:
        if key in industry:
            return team

    # Fallback: use departments_hiring from enrichment.
    departments = enrichment.get("departments_hiring") or []
    if departments:
        first = departments[0]
        return first.title() if isinstance(first, str) else str(first)

    return "Engineering"


# ─── Why-apply reasons (deterministic, max 5) ───────────────────────────

def _why_apply(
    company: Dict[str, Any],
    resume: Optional[Dict[str, Any]],
    enrichment: Dict[str, Any],
    scores: Dict[str, int],
) -> List[str]:
    """Generate personalised reasons to apply.

    Every bullet is grounded in either the company record, enrichment
    data, or the resume/company skill overlap. No invented facts.
    """
    reasons: List[str] = []

    # 1. Hiring signal.
    hiring = enrichment.get("hiring_status_detailed") or "unknown"
    if hiring == "actively_hiring":
        open_count = enrichment.get("open_positions_count")
        if isinstance(open_count, int) and open_count > 0:
            reasons.append(
                f"Actively hiring ({open_count} open role"
                f"{'s' if open_count != 1 else ''})"
            )
        else:
            reasons.append("Actively hiring")
    elif hiring == "hiring":
        reasons.append("Currently hiring")
    elif hiring == "not_hiring":
        reasons.append("Not currently hiring")

    # 2. Funding signal.
    funding_round = (company.get("funding_round") or "").strip()
    funding_amount = (company.get("funding_amount") or "").strip()
    if funding_round and funding_amount:
        reasons.append(f"Recent funding: {funding_round} ({funding_amount})")
    elif funding_round:
        reasons.append(f"Recent funding: {funding_round}")

    # 3. Tech-stack match.
    tech_fit = scores.get("technical_fit", 0) or 0
    if tech_fit >= 70:
        reasons.append("Strong tech-stack alignment with your skills")
    elif tech_fit >= 50:
        reasons.append("Partial tech-stack alignment")

    # 4. Culture indicators.
    culture = enrichment.get("engineering_culture_indicators") or []
    if culture:
        reasons.append(
            "Culture signals: " + ", ".join(str(c) for c in culture[:3])
        )

    # 5. Industry / domain.
    industry = (company.get("industry") or "").strip()
    if industry:
        reasons.append(f"Industry match: {industry}")

    # 6. Seniority match.
    exp_level = (enrichment.get("preferred_experience_level") or "").strip()
    if exp_level and exp_level != "unknown":
        reasons.append(f"Preferred experience: {exp_level}")

    # 7. Work mode.
    work_mode = (enrichment.get("work_mode") or "").strip()
    if work_mode in ("remote", "hybrid", "onsite"):
        reasons.append(f"Work mode: {work_mode}")

    # 8. Open positions emphasis.
    open_count = enrichment.get("open_positions_count")
    if (
        isinstance(open_count, int)
        and open_count >= 5
        and "Actively hiring" not in " ".join(reasons)
    ):
        reasons.append(f"{open_count} open roles on the careers page")

    if not reasons:
        reasons.append("Limited public data — manual research recommended")

    # Cap at 5.
    return reasons[:5]


# ─── Strengths (the "already have" skills) ───────────────────────────────

def _strengths_from_resume(
    resume: Optional[Dict[str, Any]], company: Dict[str, Any]
) -> List[str]:
    """Extract skills the candidate already has that match the company."""
    if not resume:
        return []
    candidate = _candidate_skill_set(resume)
    company_skills = _company_skill_set(company)
    matched = candidate & company_skills
    # Original casing from resume.
    by_lower: Dict[str, str] = {}
    for field in (
        "skills",
        "technologies",
        "programming_languages",
        "frameworks",
        "cloud",
        "databases",
        "tools",
    ):
        for s in (resume.get(field) or []):
            v = (s or "").strip()
            if v:
                by_lower[v.lower()] = v
    out: List[str] = []
    for skill in sorted(matched):
        out.append(by_lower.get(skill, skill.title()))
    return out[:10]


# ─── Skill gaps + learning path ───────────────────────────────────────────

# Time-to-learn per skill category.
_LEARNING_TIME = (
    (("python", "javascript", "typescript", "react", "next", "vue",
      "node", "express", "django", "flask", "fastapi", "spring",
      "laravel", "html", "css", "graphql"), "1-2 weeks (familiar paradigm)"),
    (("rust", "kubernetes", "kafka", "tensorflow", "pytorch", "spark",
      "flink", "hadoop", "iceberg", "ray"), "4-8 weeks (substantial new framework)"),
    (("redis", "docker", "terraform", "ansible", "grafana", "prometheus",
      "postgresql", "mongodb", "elasticsearch", "snowflake",
      "dbt"), "2-4 weeks (mid-complexity)"),
    (("llm", "rag", "langchain", "huggingface", "vector database",
      "embeddings"), "2-4 weeks (LLM stack)"),
)


def _estimate_learning_time(skill: str) -> str:
    s = (skill or "").strip().lower()
    for keywords, label in _LEARNING_TIME:
        for kw in keywords:
            if kw in s:
                return label
    return "2-6 weeks (depends on depth)"


def _skill_gaps_and_learning(
    resume: Optional[Dict[str, Any]], company: Dict[str, Any]
) -> tuple:
    """Return (skill_gaps, learning_path) computed from the candidate's
    missing skills against the company's tech stack.

    Sprint 6: when ``company['job_intelligence']['jobs']`` is present
    (from the live careers-page scrape), the gaps are derived from the
    REAL required skills of real job listings, not just the company's
    advertised tech stack. Falls back to tech-stack when no jobs are
    available.
    """
    if not resume:
        return [], []

    candidate = _candidate_skill_set(resume)
    by_lower: Dict[str, str] = {}

    # Sprint 6: prefer real-job required skills.
    ji = company.get("job_intelligence") or {}
    real_jobs = ji.get("jobs") or []
    if real_jobs:
        from app.services.job_intelligence import (
            derive_required_skills_from_jobs,
        )
        req, nice = derive_required_skills_from_jobs(real_jobs)
        for s in req + nice:
            v = s.strip()
            if v:
                by_lower[v.lower()] = v
        target_skill_set = {s.lower() for s in req + nice}
    else:
        target_skill_set = _company_skill_set(company)
        for s in (company.get("skills") or []):
            v = (s or "").strip()
            if v:
                by_lower[v.lower()] = v
        enrichment = company.get("enrichment") or {}
        for s in (enrichment.get("tech_stack") or []):
            v = (s or "").strip()
            if v:
                by_lower.setdefault(v.lower(), v)

    missing = sorted(target_skill_set - candidate)

    gaps: List[str] = []
    for skill in missing:
        gaps.append(by_lower.get(skill, skill.title()))
        if len(gaps) >= 8:
            break

    learning_path: List[Dict[str, str]] = []
    for skill in gaps:
        learning_path.append({
            "skill": skill,
            "estimated_time": _estimate_learning_time(skill),
        })
    return gaps, learning_path


# Sprint 6: keep helper signature backward-compatible.
def _skills_from_real_jobs(company: Dict[str, Any]) -> List[str]:
    """Public helper used by build_application_strategy to surface real
    job requirements in ``interview_topics`` and ``why_apply``."""
    ji = company.get("job_intelligence") or {}
    jobs = ji.get("jobs") or []
    from app.services.job_intelligence import (
        derive_required_skills_from_jobs,
    )
    req, _ = derive_required_skills_from_jobs(jobs)
    return req


# ─── Interview difficulty estimation ──────────────────────────────────────

def _estimated_difficulty(
    enrichment: Dict[str, Any], scores: Dict[str, int]
) -> str:
    """Estimate interview difficulty from enrichment + scores.

    Heuristic signals:
      - more required_skills ⇒ harder
      - later funding stage ⇒ harder
      - senior preferred experience ⇒ harder
    """
    required = enrichment.get("required_skills") or []
    funding_round = (enrichment.get("funding_round") or "").lower()
    exp_level = (
        (enrichment.get("preferred_experience_level") or "unknown").lower()
    )
    tech_fit = scores.get("technical_fit", 0) or 0

    score = 0
    if len(required) >= 5:
        score += 2
    elif len(required) >= 3:
        score += 1

    if any(
        s in funding_round
        for s in ("series c", "series d", "series e", "series f")
    ):
        score += 1

    if any(s in exp_level for s in ("senior", "principal", "staff")):
        score += 2
    elif "mid" in exp_level:
        score += 1

    # Strong tech fit pulls down difficulty (you already know the stack).
    if tech_fit >= 70:
        score = max(0, score - 1)

    if score >= 4:
        return "Hard"
    if score >= 2:
        return "Medium"
    return "Easy"


# ─── Confidence (0..100) from data sufficiency ────────────────────────────

def _confidence_from_data(
    resume: Optional[Dict[str, Any]],
    enrichment: Dict[str, Any],
    scores: Dict[str, int],
) -> int:
    """Calculate confidence (0..100) from data sufficiency.

    Base 30. Each populated resume field adds 5–10. Each populated
    enrichment field adds 5. Match quality adds a small bonus. Capped
    at 100.
    """
    if not resume:
        return 0

    confidence = 30  # base
    if resume.get("skills"):
        confidence += 10
    if resume.get("technologies"):
        confidence += 5
    if resume.get("experience"):
        confidence += 10
    if resume.get("years_of_experience"):
        confidence += 5
    if resume.get("projects"):
        confidence += 5
    if resume.get("education"):
        confidence += 5

    enrichment_fields = (
        "hiring_status_detailed",
        "tech_stack",
        "required_skills",
        "departments_hiring",
        "funding_round",
        "investors",
        "founders",
        "primary_ai_domain",
        "careers_page_url",
        "company_website",
        "headquarters",
        "work_mode",
    )
    for f in enrichment_fields:
        if enrichment.get(f):
            confidence += 4

    tech_fit = scores.get("technical_fit", 0) or 0
    if tech_fit >= 50:
        confidence += 5

    return min(100, max(0, confidence))


# ─── Suggested projects (deterministic per industry) ─────────────────────

# Already in career_intelligence._PROJECT_TEMPLATES. Re-declared here
# only when ``generate_recommendation`` is not called (e.g. direct unit
# tests). Kept identical to avoid drift.
_PROJECT_TEMPLATES = (
    ("rag", "Production RAG chatbot", "Build an end-to-end retrieval-augmented generation system: ingestion, vector store, retrieval, LLM generation, evaluation."),
    ("agent", "Multi-agent orchestration system", "Build an autonomous agent that uses tools, plans tasks, recovers from errors, coordinates with other agents."),
    ("search", "Hybrid search engine", "Build a hybrid keyword + vector search engine with learned re-ranking, query understanding, and latency/quality benchmarks."),
    ("vision", "Image / video understanding pipeline", "Build a multimodal pipeline with data labeling, model fine-tuning, evaluation harness, deployment."),
    ("infrastructure", "Distributed training / inference platform", "Build a small-scale distributed training or inference platform with GPU scheduling, checkpointing, fault tolerance."),
    ("safety", "LLM evaluation + safety harness", "Build an eval suite for an LLM application: regression tests, adversarial probes, red-team prompts, cost/latency tracking."),
)


def _suggest_projects(
    resume: Optional[Dict[str, Any]], enrichment: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Pick up to 3 project templates based on the company's primary AI
    domain and tech stack."""
    primary = (enrichment.get("primary_ai_domain") or "").lower()
    tech = " ".join(t.lower() for t in (enrichment.get("tech_stack") or []))

    matches: List[Dict[str, Any]] = []
    for keyword, title, desc in _PROJECT_TEMPLATES:
        if keyword in primary or keyword in tech:
            matches.append({"title": title, "description": desc})
        if len(matches) >= 3:
            break

    # Fallback: if no domain match, suggest the most generic project.
    if not matches:
        matches.append({
            "title": "Production-grade REST API in your strongest language",
            "description": "Build a real production-grade API with auth, observability, tests, and CI.",
        })
    return matches


# ─── Public entry point ───────────────────────────────────────────────────

def build_application_strategy(
    company: Dict[str, Any],
    resume: Optional[Dict[str, Any]],
    enrichment: Optional[Dict[str, Any]] = None,
    scores: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """Build a personalised Application Strategy for one company.

    Combines the company record, resume profile, and enrichment data.
    Every field is derived from real inputs. If data is missing the
    field is "Unknown" or empty, never fabricated.

    Returns:
        {
            "overall_recommendation": "★★★★★ Strong Apply" | ...,
            "application_priority":     "Apply Immediately" | ...,
            "why_apply":                List[str],
            "strengths":                 List[str],   # already have
            "skill_gaps":                List[str],   # need before
            "learning_path":             List[{"skill", "estimated_time"}],
            "suggested_projects":        List[{"title", "description"}],
            "interview_topics":          List[str],
            "best_team":                 str,
            "application_strategy":      Dict[str, Any],
            "estimated_interview_difficulty": "Easy" | "Medium" | "Hard",
            "confidence":                int,         # 0..100
        }

    Sprint 5 fix: this function is additive. Called from
    ``career_intelligence.generate_recommendation`` which merges the
    returned fields into the existing recommendation dict. API contracts
    and frontend remain unchanged.
    """
    enrichment = enrichment or {}
    scores = scores or {}

    overall_fit = scores.get("overall_fit", 0) or 0
    stars = _star_rating(overall_fit)
    label = _fit_label(overall_fit)

    strengths = _strengths_from_resume(resume, company)
    skill_gaps, learning_path = _skill_gaps_and_learning(resume, company)
    why = _why_apply(company, resume, enrichment, scores)
    best_team = _best_team_for_company(company, enrichment)
    difficulty = _estimated_difficulty(enrichment, scores)
    confidence = _confidence_from_data(resume, enrichment, scores)

    # Existing career_intelligence.build_interview_prep already
    # produces a richer structure; here we expose a flat list of the
    # "likely_topics" subset for the requested simple schema.
    interview_topics: List[str] = list(
        (enrichment.get("likely_topics") or [])
        if isinstance(enrichment.get("likely_topics"), list)
        else []
    )
    # Sprint 6: if real job listings are available, prioritise the
    # skills actually required by those listings. Real-job signals
    # dominate tech-stack heuristics.
    real_job_skills = _skills_from_real_jobs(company)
    if real_job_skills:
        # De-dupe, preserve order, prefer real-job skills.
        seen: set = set()
        merged: List[str] = []
        for s in real_job_skills + interview_topics:
            if isinstance(s, str) and s.lower() not in seen:
                seen.add(s.lower())
                merged.append(s)
        interview_topics = merged[:8]
    # If no enrichment-driven topics, derive from company tech stack.
    if not interview_topics:
        for s in (enrichment.get("tech_stack") or [])[:5]:
            if isinstance(s, str):
                interview_topics.append(s)
    if not interview_topics:
        interview_topics = ["System design", "Behavioural", "Domain knowledge"]

    projects = _suggest_projects(resume, enrichment)

    # Sprint 6: include the hiring summary (counts of engineering,
    # intern, graduate, remote, visa-sponsored roles) so the
    # dashboard can show "6 open roles · 4 engineering" without
    # re-implementing the parser.
    hiring_summary = (company.get("job_intelligence") or {}).get(
        "hiring_summary"
    )

    # Sprint 7: compute the explainable Opportunity Assessment.
    # Add an inner dict ``opportunity`` so the existing top-level keys
    # (overall_recommendation, application_priority, etc.) are NOT
    # replaced. ``opportunity`` is a new key — additive only.
    from app.services.opportunity_intelligence import (
        compute_opportunity_intelligence,
    )
    opportunity = compute_opportunity_intelligence(
        company=company,
        resume=resume,
        strategy={
            "skill_gaps": skill_gaps,
            "confidence": confidence,
            "estimated_interview_difficulty": difficulty,
        },
        enrichment=enrichment,
        hiring_summary=hiring_summary,
        scores=scores,
    )

    return {
        "overall_recommendation": f"{stars} {label}",
        "why_apply": why,
        "strengths": strengths,
        "skill_gaps": skill_gaps,
        "learning_path": learning_path,
        "suggested_projects": projects,
        "interview_topics": interview_topics,
        "best_team": best_team,
        "estimated_interview_difficulty": difficulty,
        "confidence": confidence,
        # Sprint 6 — add job_intelligence summary (real jobs) when available.
        "hiring_summary": hiring_summary,
        # Sprint 7 — explainable opportunity intelligence (additive).
        "opportunity": opportunity,
    }