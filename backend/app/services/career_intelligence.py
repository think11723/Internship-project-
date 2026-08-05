"""Career Intelligence Engine.

Pure-deterministic recommendation generator. No LLM dependency.
Uses ONLY data that already exists in the cache:

  - Company's enriched fields (tech_stack, required_skills, hiring,
    funding, founders, investors, work_mode, primary_ai_domain, …)
  - Latest uploaded resume's skills / technologies / experience / projects

Every field falls back to None or "unknown" when the source is
silent. No hallucinations. If confidence is low, the recommendation
explicitly says so.

The output is a structured per-company recommendation attached to
each cache record under the ``recommendation`` key.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# Skill-learning-time heuristic (in weeks). Used by the
# skill-gap analysis to estimate how long it would take the candidate
# to close each gap.
_LEARNING_TIME = [
    (["python", "javascript", "typescript", "react", "next.js", "vue",
      "node.js", "express", "django", "flask", "fastapi", "spring boot",
      "laravel", "html", "css", "graphql"], "1-2 weeks (familiar paradigm)"),
    (["rust", "kubernetes", "kafka", "tensorflow", "pytorch", "spark",
      "flink", "hadoop", "iceberg"], "4-8 weeks (substantial new framework)"),
    (["redis", "docker", "terraform", "ansible", "grafana", "prometheus",
      "postgresql", "mongodb", "elasticsearch", "kafka", "snowflake",
      "dbt"], "2-4 weeks (mid-complexity)"),
    (["llm", "rag", "langchain", "langgraph", "huggingface",
      "vector database", "embeddings"], "2-4 weeks (LLM stack)"),
    ([], "2-6 weeks (depends on depth)"),
]


# Project-template heuristics keyed on the company's primary AI
# domain. We never invent things the company doesn't already hint at;
# we suggest projects that USE their tech stack.
_PROJECT_TEMPLATES = [
    ("rag", "Production RAG chatbot using {lang}",
     "Build an end-to-end retrieval-augmented generation system: document ingestion pipeline, vector store, retrieval with re-ranking, LLM generation with citations, evaluation harness, and a chat UI. Deploy to production with observability."),
    ("agent", "Multi-agent orchestration system",
     "Build an autonomous agent that uses tools, plans tasks, recovers from errors, and coordinates with other agents. Include planning, memory, observability, and an evaluation suite. Demonstrates the patterns this company likely builds."),
    ("search", "Hybrid search engine",
     "Build a hybrid keyword + vector search engine: BM25 + embedding retrieval, learned re-ranking, query understanding, latency/quality benchmarks. Solves a real problem at the company."),
    ("vision", "Production image / video understanding pipeline",
     "Build an end-to-end multimodal pipeline: data labeling, model fine-tuning, evaluation harness, deployment, latency + cost monitoring. Mirrors the company's domain."),
    ("infrastructure", "Distributed training / inference platform",
     "Build a small-scale distributed training or inference platform with GPU scheduling, checkpointing, fault tolerance, and observability. Demonstrates systems thinking."),
    ("safety", "LLM evaluation + safety harness",
     "Build an eval suite for an LLM application: regression tests, adversarial probes, red-team prompts, cost/latency tracking, alignment metrics. Demonstrates production discipline."),
]


def _candidate_skill_set(resume: Dict[str, Any]) -> set:
    """Normalise every skill the candidate has into a lowercase set."""
    s = set()
    for field in ("skills", "technologies", "programming_languages", "tools",
                  "frameworks"):
        for v in (resume.get(field) or []):
            v = (v or "").strip().lower()
            if v:
                s.add(v)
    return s


def _norm(v: Any) -> str:
    return (v or "").strip().lower()


def _estimate_learning_time(skill: str) -> str:
    s = (skill or "").strip().lower()
    for keywords, label in _LEARNING_TIME:
        for kw in keywords:
            if kw in s:
                return label
    return _LEARNING_TIME[-1][1]


# ─── Scores (each returns an int 0..100) ───────────────────────────────
def _score_hiring_confidence(enrichment: Dict[str, Any]) -> int:
    status = enrichment.get("hiring_status_detailed", "unknown") or "unknown"
    base = {
        "actively_hiring": 85,
        "hiring": 55,
        "not_hiring": 10,
        "unknown": 35,
    }.get(status, 35)
    count = enrichment.get("open_positions_count")
    if isinstance(count, int) and count > 0:
        if count >= 10:
            base = min(100, base + 10)
        elif count >= 5:
            base = min(100, base + 5)
    if status == "not_hiring":
        base = max(0, base - 30)
    return max(0, min(100, base))


def _score_tech_fit(resume: Dict[str, Any], enrichment: Dict[str, Any]) -> int:
    cand = _candidate_skill_set(resume)
    tech_stack = enrichment.get("tech_stack") or []
    required = enrichment.get("required_skills") or []
    if not tech_stack and not required:
        return 50
    matched = sum(
        1
        for x in list(tech_stack) + list(required)
        if _norm(x) in cand
    )
    total = len(tech_stack) + len(required)
    return max(0, min(100, int((matched / max(total, 1)) * 100)))


def _score_culture_fit(resume: Dict[str, Any], enrichment: Dict[str, Any]) -> int:
    """Heuristic: culture indicators that match common candidate
    profiles (fast-growing, startup, YC alum, remote-friendly)."""
    score = 50
    for ind in enrichment.get("engineering_culture_indicators") or []:
        n = ind.lower()
        if any(k in n for k in ("fast", "startup", "yc ", "y combinator",
                                 "remote-first", "early-stage")):
            score += 12
        if "open-source" in n:
            score += 6
    if enrichment.get("work_mode") == "remote":
        score += 8
    yrs = (resume.get("years_of_experience") or "").lower()
    if "senior" in enrichment.get("preferred_experience_level", "").lower():
        score += 5
    if "10+" in yrs or "10 +" in yrs or "10-year" in yrs or "15-year" in yrs:
        score += 3
    return max(0, min(100, score))


def _score_growth_opportunity(enrichment: Dict[str, Any]) -> int:
    amount = enrichment.get("funding_amount") or ""
    funding_round = enrichment.get("funding_round") or ""
    score = 40
    digits = "".join(c for c in amount if c.isdigit() or c == ".")
    try:
        n = float(digits.rstrip(".")) if digits else 0
    except ValueError:
        n = 0
    unit = amount.upper()
    if "B" in unit and n > 0:
        score = min(100, 50 + int(n * 10))  # Series B / C / D / etc.
    elif "M" in unit and n > 0:
        score = min(95, 40 + int(n / 5))
    round_score = {
        "Pre-Seed": 25, "Pre-seed": 25, "Seed": 50,
        "Series A": 65, "Series B": 75, "Series C": 85,
        "Series D": 92, "Series E": 96, "Series F": 98,
    }.get(funding_round, 0)
    score = max(score, round_score)
    if enrichment.get("hiring_status_detailed") == "actively_hiring":
        score = min(100, score + 5)
    return max(0, min(100, score))


def _score_learning_potential(
    resume: Dict[str, Any], enrichment: Dict[str, Any]
) -> int:
    """Inverse of tech fit — more overlap means less new to learn,
    less overlap means more learning opportunity."""
    tf = _score_tech_fit(resume, enrichment)
    tech_stack_count = len(enrichment.get("tech_stack") or [])
    primary = (enrichment.get("primary_ai_domain") or "").strip()
    base = 100 - tf
    if primary:
        base = min(100, base + 10)  # frontier domain bonus
    if tech_stack_count >= 5:
        base = min(100, base + 5)  # diverse stack → more to learn
    return max(0, min(100, base))


def _score_resume_readiness(resume: Dict[str, Any]) -> int:
    """Heuristic based on completeness of the resume."""
    score = 30
    if resume.get("name"):
        score += 5
    if resume.get("email"):
        score += 5
    if resume.get("summary"):
        score += 5
    skills = resume.get("skills") or []
    if len(skills) >= 5:
        score += 15
    elif len(skills) >= 1:
        score += 5
    techs = resume.get("technologies") or []
    if len(techs) >= 3:
        score += 10
    if resume.get("experience"):
        score += 10
    if resume.get("education"):
        score += 5
    if resume.get("projects"):
        score += 5
    if resume.get("years_of_experience"):
        score += 5
    return max(0, min(100, score))


def _overall_fit(scores: Dict[str, int]) -> int:
    """Composite of technical, culture, growth, learning.
    Hiring + resume-readiness are reported separately so the
    candidate sees where they stand on each axis."""
    weighted = (
        scores["technical_fit"] * 0.35
        + scores["culture_fit"] * 0.20
        + scores["growth_opportunity"] * 0.25
        + scores["learning_potential"] * 0.20
    )
    return max(0, min(100, int(weighted)))


def _determine_priority(scores: Dict[str, int]) -> str:
    fit = scores["overall_fit"]
    hiring = scores["hiring_confidence"]
    growth = scores["growth_opportunity"]
    ready = scores["resume_readiness"]
    if fit >= 70 and hiring >= 60 and growth >= 60 and ready >= 60:
        return "Apply Immediately"
    if fit >= 55 and hiring >= 45:
        return "Apply This Week"
    if fit >= 35:
        return "Monitor"
    if fit >= 20:
        return "Wait"
    return "Skip"


# ─── Explanations ──────────────────────────────────────────────────────
def _build_why(
    resume: Dict[str, Any],
    enrichment: Dict[str, Any],
    scores: Dict[str, int],
    gaps: List[Dict[str, Any]],
) -> List[str]:
    bullets: List[str] = []
    cand = _candidate_skill_set(resume)
    tech = enrichment.get("tech_stack") or []
    matched = [t for t in tech if _norm(t) in cand]
    if matched:
        if len(matched) == 1:
            bullets.append(f"{matched[0]} is in your stack")
        elif len(matched) <= 3:
            bullets.append(f"{', '.join(matched)} match your skills")
        else:
            bullets.append(
                f"{len(matched)} core technologies match your stack "
                f"({', '.join(matched[:3])}, …)"
            )
    missing = [g["skill"] for g in gaps if g.get("category") == "critical"][:3]
    if missing:
        bullets.append(
            f"Missing critical skills: {', '.join(missing)}"
        )
    funding = enrichment.get("funding_amount")
    funding_round = enrichment.get("funding_round")
    if funding or funding_round:
        bits = []
        if funding_round:
            bits.append(funding_round)
        if funding:
            bits.append(funding)
        bullets.append(f"Recent funding: {' / '.join(bits)}")
    hs = enrichment.get("hiring_status_detailed", "")
    if hs == "actively_hiring":
        opn = enrichment.get("open_positions_count")
        if opn:
            bullets.append(
                f"Actively hiring ({opn} open role{'s' if opn != 1 else ''})"
            )
        else:
            bullets.append("Actively hiring")
    wm = enrichment.get("work_mode")
    if wm == "remote":
        bullets.append("Remote-friendly")
    elif wm == "hybrid":
        bullets.append("Hybrid work environment")
    primary = (enrichment.get("primary_ai_domain") or "").strip()
    if primary and scores["learning_potential"] >= 60:
        bullets.append(f"Frontier domain: {primary}")
    if scores["overall_fit"] < 30:
        bullets.append("Confidence is low — limited enrichment data available")
    return bullets[:8]


# ─── Skill gaps ────────────────────────────────────────────────────────
def _build_skill_gaps(
    resume: Dict[str, Any], enrichment: Dict[str, Any]
) -> List[Dict[str, Any]]:
    cand = _candidate_skill_set(resume)
    tech_stack = enrichment.get("tech_stack") or []
    required = enrichment.get("required_skills") or []
    gaps: List[Dict[str, Any]] = []
    seen = set()
    for skill in tech_stack:
        if _norm(skill) in cand or _norm(skill) in seen:
            continue
        seen.add(_norm(skill))
        gaps.append({
            "skill": skill,
            "category": "critical",
            "reason": "Core technology at the company",
            "estimated_learning_time": _estimate_learning_time(skill),
            "suggested_actions": _actions_for_skill(skill),
        })
    for skill in required:
        if _norm(skill) in cand or _norm(skill) in seen:
            continue
        seen.add(_norm(skill))
        gaps.append({
            "skill": skill,
            "category": "important",
            "reason": "Listed in job requirements",
            "estimated_learning_time": _estimate_learning_time(skill),
            "suggested_actions": _actions_for_skill(skill),
        })
    return gaps[:8]


def _actions_for_skill(skill: str) -> List[str]:
    """Resource suggestions keyed on the skill name. Only public,
    well-known resources — never invent URLs or course names."""
    s = skill.lower()
    actions: List[str] = []
    if any(k in s for k in ["python", "fastapi", "django", "flask"]):
        actions += ["Build a CRUD REST API with FastAPI + PostgreSQL",
                    "Read the official FastAPI tutorial"]
    elif any(k in s for k in ["rust", "go", "java", "kotlin", "scala"]):
        actions += ["Build a small CLI tool in this language",
                    "Solve 5 Advent-of-Code problems in it"]
    elif any(k in s for k in ["kubernetes", "docker", "terraform"]):
        actions += ["Containerize a personal project end-to-end",
                    "Deploy it to a free Kubernetes cluster (k3s/EKS/GKE)"]
    elif any(k in s for k in ["kafka", "rabbitmq", "redis"]):
        actions += ["Build a pub-sub demo with at-least-once delivery",
                    "Benchmark throughput vs your DB"]
    elif any(k in s for k in ["react", "next.js", "vue", "svelte"]):
        actions += ["Build a small SPA with this framework",
                    "Add server-side rendering"]
    elif any(k in s for k in ["tensorflow", "pytorch", "sklearn"]):
        actions += ["Train a small model on a public dataset",
                    "Add an evaluation harness"]
    elif any(k in s for k in ["llm", "rag", "langchain"]):
        actions += ["Build a RAG chatbot with eval + observability"]
    elif any(k in s for k in ["postgres", "mysql", "redis"]):
        actions += ["Practice schema design + query optimization"]
    elif "aws" in s or "gcp" in s or "azure" in s:
        actions += ["Deploy a real workload on this cloud"]
    else:
        actions += [f"Build a small project in {skill}", f"Read one authoritative source on {skill}"]
    return actions[:3]


# ─── Project recommendations ───────────────────────────────────────────
def _suggest_projects(
    resume: Dict[str, Any], enrichment: Dict[str, Any]
) -> List[Dict[str, Any]]:
    tech = enrichment.get("tech_stack") or []
    primary = (enrichment.get("primary_ai_domain") or "").lower()
    candidates = []
    for keyword, title, desc in _PROJECT_TEMPLATES:
        if keyword in primary or keyword in " ".join(tech).lower():
            lang = ""
            for t in tech:
                low = t.lower()
                if low in ("python", "go", "rust", "typescript", "java", "kotlin"):
                    lang = t
                    break
            title_filled = title.format(lang=lang) if "{lang}" in title else title
            candidates.append({
                "title": title_filled,
                "description": desc,
                "skills_demonstrated": tech[:3] if tech else [keyword],
                "estimated_duration": "2-3 weeks",
                "tech_used": [keyword] + tech[:2],
            })
    if not candidates and tech:
        lang = ""
        for t in tech:
            low = t.lower()
            if low in ("python", "go", "rust", "typescript", "java", "kotlin"):
                lang = t
                break
        if not lang and tech:
            lang = tech[0]
        candidates.append({
            "title": f"Production-grade {lang} backend service" if lang else "Open-source contribution",
            "description": f"Build a REST/GraphQL service in {lang} with PostgreSQL, JWT auth, observability, and load tests." if lang else "Contribute a meaningful PR to an active OSS project.",
            "skills_demonstrated": tech[:3],
            "estimated_duration": "2-3 weeks",
            "tech_used": tech[:3],
        })
    return candidates[:3]


# ─── Application strategy ───────────────────────────────────────────
def _application_strategy(priority: str, scores: Dict[str, int]) -> Dict[str, Any]:
    if priority == "Apply Immediately":
        return {
            "should_apply_today": True,
            "should_wait": False,
            "improve_resume_first": False,
            "build_project_first": False,
            "contact_recruiter": True,
            "use_linkedin": True,
            "cold_email": True,
            "reasoning": "Strong fit, actively hiring, recent funding. Strike while the window is open.",
        }
    if priority == "Apply This Week":
        return {
            "should_apply_today": False,
            "should_wait": False,
            "improve_resume_first": True,
            "build_project_first": False,
            "contact_recruiter": True,
            "use_linkedin": True,
            "cold_email": True,
            "reasoning": "Good fit. Tighten the resume with role-specific keywords this week and apply Monday.",
        }
    if priority == "Monitor":
        return {
            "should_apply_today": False,
            "should_wait": True,
            "improve_resume_first": True,
            "build_project_first": True,
            "contact_recruiter": False,
            "use_linkedin": True,
            "cold_email": False,
            "reasoning": "Marginal fit. Build a relevant project first; revisit in 30 days.",
        }
    return {
        "should_apply_today": False,
        "should_wait": True,
        "improve_resume_first": True,
        "build_project_first": True,
        "contact_recruiter": False,
        "use_linkedin": False,
        "cold_email": False,
        "reasoning": "Significant skill gaps. Focus on foundational skills first.",
    }


# ─── Interview prep ───────────────────────────────────────────────────
def _interview_prep(
    resume: Dict[str, Any], enrichment: Dict[str, Any]
) -> Dict[str, Any]:
    tech = [t for t in (enrichment.get("tech_stack") or [])]
    primary = (enrichment.get("primary_ai_domain") or "").lower()
    exp = (enrichment.get("preferred_experience_level") or "").lower()

    topics = ["System design fundamentals", "Past project walkthroughs"]
    coding = ["Data structures (hash maps, trees, graphs)", "Async / concurrent code", "API design"]
    sys_design = ["Designing a scalable API", "Database schema design", "Caching strategies"]
    behavioral = [
        "Tell me about a project you're proud of",
        "Tell me about a time you disagreed with a teammate",
        "Why this company?",
    ]
    if any(t in tech for t in ["kubernetes", "kafka", "redis"]):
        sys_design.append("Distributed systems design")
    if any(k in primary for k in ("rag", "agent", "llm", "search")):
        topics.append("LLM application architecture")
        topics.append("Vector databases and embedding strategies")
    if "rag" in primary:
        topics.append("Retrieval evaluation metrics")
    if exp == "senior":
        sys_design += ["Microservices architecture", "Database scaling"]
    return {
        "likely_topics": topics,
        "likely_coding_questions": coding,
        "likely_system_design_topics": sys_design,
        "likely_behavioral_topics": behavioral,
        "company_specific_preparation": [
            f"Read their recent {primary or 'company'} announcement",
            f"Prepare two questions about their use of {', '.join(tech[:2]) if tech else 'their stack'}",
        ],
    }


# ─── Action plan ─────────────────────────────────────────────────────
def _action_plan(
    priority: str, gaps: List[Dict[str, Any]], projects: List[Dict[str, Any]]
) -> Dict[str, Any]:
    today = ["Quantify one bullet on your resume with a metric"]
    this_week = ["Refresh your resume's skills section with keywords from their job spec"]
    next_month: List[str] = []
    if priority in ("Apply Immediately", "Apply This Week"):
        today.append("Submit the application via their careers page")
        if gaps:
            this_week.append(f"Begin studying: {gaps[0]['skill']}")
        if projects:
            next_month.append(f"Build the recommended project: {projects[0]['title']}")
    elif priority == "Monitor":
        if gaps:
            this_week.append(f"Start learning: {gaps[0]['skill']}")
        if projects:
            next_month.append(f"Build: {projects[0]['title']}")
    else:
        if gaps:
            this_week.append(f"Foundational study: {gaps[0]['skill']}")
        next_month.append("Build a portfolio project in this domain")
    return {
        "today": today[:3],
        "this_week": this_week[:3],
        "next_month": next_month[:3],
        "roadmap": (
            "From " + priority + " to Apply Immediately in 4–8 weeks of "
            "focused skill-building and project work."
        ),
    }


# ─── Resume improvements ───────────────────────────────────────────
def _resume_improvements(
    resume: Dict[str, Any], enrichment: Dict[str, Any]
) -> Dict[str, Any]:
    cand = _candidate_skill_set(resume)
    tech_stack = enrichment.get("tech_stack") or []
    missing_keywords = [
        t for t in tech_stack[:6]
        if _norm(t) not in cand
    ][:5]
    yrs = resume.get("years_of_experience") or ""
    return {
        "weaknesses": [
            "Bullets don't quantify impact (use %, $, ms, QPS)",
            "Project blurbs emphasize implementation over outcome",
        ],
        "missing_keywords": missing_keywords,
        "missing_achievements": [
            "Open-source contributions with linked PRs",
            "Production scale (users served, QPS, uptime)",
            "Cross-functional collaboration (PMs, designers, ML researchers)",
        ],
        "suggested_bullet_improvements": [
            "Replace 'Built X' with 'Built X that serves N users at M QPS'",
            "Replace 'Optimized Y' with 'Reduced Y latency from A to B ms (X% improvement)'",
            "Add the metric, then add the action that produced it",
        ],
        "ats_improvements": [
            f"Add '{kw}' to skills section if you have production experience"
            for kw in missing_keywords
        ],
        "seniority_signals": [
            f"Candidate's years_of_experience is {yrs!r}; consider clarifying with month count",
        ],
    }


# ─── Public entry point ────────────────────────────────────────────
def generate_recommendation(
    company: Dict[str, Any], resume: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Build a per-company recommendation dict.

    Pure deterministic. ``resume`` may be None if no resume is uploaded;
    in that case scores degrade gracefully and ``data_sufficiency``
    is reported as ``"insufficient"``.

    Sprint 5: this function now also calls
    ``application_strategy.build_application_strategy`` and merges the
    returned fields (overall_recommendation, why_apply, strengths,
    skill_gaps, learning_path, suggested_projects, interview_topics,
    best_team, estimated_interview_difficulty, confidence) into the
    result. The merge is additive — existing keys are preserved.
    """
    enrichment = company.get("enrichment") or {}

    # Sprint 5: import lazily to avoid an import cycle (career_intelligence
    # already imports many services; application_strategy is pure).
    from app.services.application_strategy import build_application_strategy

    if resume is None:
        recommendation: Dict[str, Any] = {
            "scores": {
                "hiring_confidence": _score_hiring_confidence(enrichment),
                "technical_fit": 0,
                "culture_fit": 0,
                "growth_opportunity": _score_growth_opportunity(enrichment),
                "learning_potential": 0,
                "resume_readiness": 0,
                "overall_fit": 0,
            },
            "application_priority": "Upload your resume to get a personalized recommendation",
            "why": ["Upload your resume to unlock fit scoring, skill-gap analysis, and personalized projects."],
            "skill_gaps": [],
            "project_recommendations": [],
            "resume_improvements": {},
            "application_strategy": {
                "should_apply_today": False,
                "should_wait": True,
                "improve_resume_first": True,
                "build_project_first": False,
                "contact_recruiter": False,
                "use_linkedin": False,
                "cold_email": False,
                "reasoning": "Upload your resume to generate a tailored recommendation.",
            },
            "interview_prep": {},
            "action_plan": {
                "today": ["Upload your resume"],
                "this_week": ["Wait for recommendation"],
                "next_month": ["Apply based on scores"],
                "roadmap": "Upload resume to unlock personalised recommendations.",
            },
            "data_sufficiency": "insufficient",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "input_resume_id": None,
            "input_company": company.get("name", ""),
        }
        # Sprint 5: merge application strategy fields even when no resume
        # is uploaded (data is Unknown / "Insufficient Data" labels).
        scores_insufficient = recommendation["scores"]
        recommendation.update(
            build_application_strategy(
                company, resume, enrichment=enrichment, scores=scores_insufficient
            )
        )
        return recommendation

    scores = {
        "hiring_confidence": _score_hiring_confidence(enrichment),
        "technical_fit": _score_tech_fit(resume, enrichment),
        "culture_fit": _score_culture_fit(resume, enrichment),
        "growth_opportunity": _score_growth_opportunity(enrichment),
        "learning_potential": _score_learning_potential(resume, enrichment),
        "resume_readiness": _score_resume_readiness(resume),
    }
    scores["overall_fit"] = _overall_fit(scores)

    priority = _determine_priority(scores)
    gaps = _build_skill_gaps(resume, enrichment)
    projects = _suggest_projects(resume, enrichment)
    strategy = _application_strategy(priority, scores)
    prep = _interview_prep(resume, enrichment)
    plan = _action_plan(priority, gaps, projects)
    improvements = _resume_improvements(resume, enrichment)
    why = _build_why(resume, enrichment, scores, gaps)

    recommendation = {
        "scores": scores,
        "application_priority": priority,
        "why": why,
        "skill_gaps": gaps,
        "project_recommendations": projects,
        "resume_improvements": improvements,
        "application_strategy": strategy,
        "interview_prep": prep,
        "action_plan": plan,
        "data_sufficiency": "complete",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_resume_id": resume.get("id"),
        "input_company": company.get("name", ""),
    }

    # Sprint 5: merge the personalised Application Strategy fields
    # (overall_recommendation, why_apply, strengths, skill_gaps,
    # learning_path, suggested_projects, interview_topics, best_team,
    # estimated_interview_difficulty, confidence) into the existing
    # recommendation. Existing keys are preserved; new keys are added.
    recommendation.update(
        build_application_strategy(
            company, resume, enrichment=enrichment, scores=scores
        )
    )

    return recommendation


def aggregate_recommendation_metrics(
    companies: List[Dict[str, Any]], resume: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Compute portfolio-level aggregates for the dashboard."""
    if not companies:
        return {
            "priority_distribution": {},
            "average_scores": {},
            "top_priority": None,
            "top_priority_company": None,
        }
    priority_counts: Dict[str, int] = {}
    score_sums = {
        "hiring_confidence": 0, "technical_fit": 0, "culture_fit": 0,
        "growth_opportunity": 0, "learning_potential": 0,
        "resume_readiness": 0, "overall_fit": 0,
    }
    score_count = 0
    top_priority = None
    top_priority_company = None
    top_score = -1
    order = ["Apply Immediately", "Apply This Week", "Monitor", "Wait", "Skip"]
    priority_rank = {p: i for i, p in enumerate(order)}
    for c in companies:
        rec = c.get("recommendation")
        if not isinstance(rec, dict):
            continue
        p = rec.get("application_priority")
        if isinstance(p, str):
            priority_counts[p] = priority_counts.get(p, 0) + 1
            if (top_priority is None
                    or priority_rank.get(p, 99) < priority_rank.get(top_priority, 99)):
                top_priority = p
                top_priority_company = c.get("name")
        for k in score_sums:
            v = rec.get("scores", {}).get(k)
            if isinstance(v, (int, float)):
                score_sums[k] += v
        score_count += 1
    averages = (
        {k: round(v / max(score_count, 1)) for k, v in score_sums.items()}
        if score_count > 0
        else {}
    )
    return {
        "priority_distribution": priority_counts,
        "average_scores": averages,
        "top_priority": top_priority,
        "top_priority_company": top_priority_company,
        "data_sufficiency": "complete" if score_count > 0 else "insufficient",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_resume_id": resume.get("id") if isinstance(resume, dict) else None,
    }
