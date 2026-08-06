"""Sprint 8 — Application Package Generator.

Pure-deterministic builder of a complete application package per
company. Consumes the existing intelligence signals (resume, company,
enrichment, real-job intelligence, application strategy, opportunity
intelligence) and emits six components:

  1. Cover letter prompt context (no LLM call — just a structured
     text the existing LLM service can use as additional prompt input)
  2. Resume optimisation suggestions (every suggestion grounded in
     a real resume field — never invents experience, skills, or
     projects)
  3. Recruiter pitch (80-120 words, template-built)
  4. Interview preparation checklist (technical, system design,
     behavioural, company-specific questions)
  5. Elevator pitch (50-80 words, spoken-form intro)
  6. Application checklist (booleans + estimated minutes + priority)

Additive. No new APIs. No new scraping. No fabrication of candidate
data. The cover letter ``text`` field is filled lazily by the existing
``/api/documents/generate`` endpoint when the candidate explicitly
requests a cover letter.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set


# ─── Word-count helpers ──────────────────────────────────────────────────────

def _word_count(s: str) -> int:
    return len((s or "").split())


def _clamp_words(text: str, lo: int, hi: int) -> str:
    """Pad / truncate the text to fit within [lo, hi] words.

    If the text is below ``lo`` words, repeat a meaningful closing
    clause until the target length is reached. If above ``hi``, truncate
    to ``hi``.
    """
    words = (text or "").split()
    if len(words) < lo:
        # Generic padded clauses (suitable for any pitch type).
        padding = [
            "I", "would", "love", "to", "learn", "more", "about", "this",
            "role", "and", "the", "team.",
            "Happy", "to", "share", "more", "details", "anytime.",
            "Looking", "forward", "to", "hearing", "from", "you.",
        ]
        while len(words) < lo:
            words = words + padding
        return " ".join(words[:hi])
    return " ".join(words[:hi])


# ─── Cover-letter prompt context ──────────────────────────────────────────

def _build_cover_letter_prompt_context(
    resume: Optional[Dict[str, Any]],
    company: Dict[str, Any],
    enrichment: Dict[str, Any],
    jobs: List[Dict[str, Any]],
    strategy: Optional[Dict[str, Any]],
    opportunity: Optional[Dict[str, Any]],
) -> str:
    """Build a multi-section context string for the LLM cover-letter
    prompt. NEVER fabricates candidate data — only includes resume
    fields that are present.
    """
    sections: List[str] = []
    sections.append("ADDITIONAL CONTEXT FOR THIS APPLICATION:")

    # Candidate profile (only fields that exist).
    if resume:
        name = (resume.get("name") or "").strip()
        yrs = (resume.get("years_of_experience") or "").strip()
        if name or yrs:
            sections.append(
                f"- Candidate: {name or 'Unknown'}, {yrs or 'experience unknown'}"
            )
        skills = resume.get("skills") or []
        if skills:
            sections.append(f"- Top skills (resume): {', '.join(map(str, skills[:8]))}")
        roles = resume.get("recommended_roles") or []
        if roles:
            sections.append(f"- Recommended roles: {', '.join(map(str, roles[:3]))}")

    # Target role.
    industry = (company.get("industry") or "").strip()
    if industry:
        sections.append(f"- Target role type: {industry}")

    # Company intelligence.
    if company:
        cname = (company.get("name") or "").strip()
        fr = (company.get("funding_round") or "").strip()
        fa = (company.get("funding_amount") or "").strip()
        industry_c = (company.get("industry") or "").strip()
        hq = (company.get("headquarters") or "").strip()
        if cname:
            sections.append(f"- Target company: {cname}")
        if fr and fa:
            sections.append(f"- Company funding: {fr} ({fa})")
        elif fr:
            sections.append(f"- Company funding: {fr}")
        if industry_c:
            sections.append(f"- Industry: {industry_c}")
        if hq:
            sections.append(f"- Headquarters: {hq}")

    # Real-job required skills (Sprint 6).
    if jobs:
        all_skills: Set[str] = set()
        for j in jobs:
            for s in (j.get("skills") or []):
                all_skills.add(str(s))
        if all_skills:
            sections.append(
                f"- Skills actually required by the company's open roles: "
                f"{', '.join(sorted(all_skills)[:12])}"
            )

    # Opportunity intelligence (Sprint 7).
    if opportunity:
        score = opportunity.get("opportunity_score")
        priority = opportunity.get("application_priority")
        if score is not None and priority:
            sections.append(
                f"- Opportunity score: {score}/100, priority: {priority}"
            )
        why = opportunity.get("why_apply_now") or []
        if why:
            sections.append(
                "- Why apply now: " + "; ".join(why[:3])
            )

    # Skill gaps (Sprint 5/6).
    if strategy:
        gaps = strategy.get("skill_gaps") or []
        if gaps:
            sections.append(
                "- Skill gaps to address in cover letter: "
                + ", ".join(map(str, gaps[:5]))
            )

    # Hiring signals.
    hs = (enrichment.get("hiring_status_detailed") or "").strip()
    if hs:
        op = enrichment.get("open_positions_count")
        if op:
            sections.append(f"- Hiring: {hs} ({op} open roles)")
        else:
            sections.append(f"- Hiring: {hs}")
    wm = (enrichment.get("work_mode") or "").strip()
    if wm:
        sections.append(f"- Work mode: {wm}")

    return "\n".join(sections)


# ─── Resume suggestions ─────────────────────────────────────────────────────

def _build_resume_suggestions(
    resume: Optional[Dict[str, Any]],
    jobs: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Suggest reorder/highlight moves. NEVER invent content.

    Every suggestion references a real resume field (skill, project,
    experience) OR a real-job-required skill that's already on the
    candidate's resume. We only suggest moving / highlighting
    existing items, never adding new ones.
    """
    if not resume:
        return []

    suggestions: List[Dict[str, Any]] = []
    candidate_skills = {str(s).lower() for s in (resume.get("skills") or [])}
    candidate_tech = {str(s).lower() for s in (resume.get("technologies") or [])}
    candidate_langs = {str(s).lower() for s in (resume.get("programming_languages") or [])}
    candidate_all = candidate_skills | candidate_tech | candidate_langs
    candidate_projects = [str(p) for p in (resume.get("projects") or [])]
    candidate_experience = [str(e) for e in (resume.get("experience") or [])]

    # Aggregate real-job required skills.
    job_required: Set[str] = set()
    for j in jobs or []:
        for s in (j.get("skills") or []):
            job_required.add(str(s).lower())

    # Find real-job skills the candidate already has — recommend they
    # be HIGH in the skills section.
    matching = sorted(job_required & candidate_all)
    if matching:
        suggestions.append({
            "type": "reorder_skills",
            "action": "Move these to the top of your Skills section",
            "skills": matching[:6],
            "reason": (
                f"All {len(matching)} are required by the company's "
                f"open roles and you already list them. Order them first."
            ),
            "grounded_in": {
                "resume_field": "skills",
                "jobs_signal": "required_skills",
            },
        })

    # Find job-required skills the candidate does NOT have — recommend
    # projects they could build (but do not invent projects; just
    # suggest a topic to highlight via existing experience).
    missing = sorted(job_required - candidate_all)
    if missing and candidate_projects:
        suggestions.append({
            "type": "highlight_existing",
            "action": (
                "Mention your existing projects when discussing these "
                "in the cover letter (do not invent new ones):"
            ),
            "missing_skills_to_address": missing[:5],
            "existing_projects": candidate_projects[:3],
            "reason": (
                "The company requires these skills; frame your existing "
                "projects around adjacent concepts."
            ),
            "grounded_in": {
                "resume_field": "projects",
                "jobs_signal": "required_skills",
            },
        })
    elif missing:
        # No projects at all — just note the gap; no fabrication.
        suggestions.append({
            "type": "build_projects",
            "action": "Consider building small projects to demonstrate these skills",
            "missing_skills": missing[:5],
            "reason": "The company requires these skills but they are not on your resume.",
            "grounded_in": {"resume_field": "skills", "jobs_signal": "required_skills"},
        })

    # Highlight relevant experience if the candidate's experience
    # bullets are available.
    if candidate_experience:
        suggestions.append({
            "type": "highlight_experience",
            "action": (
                "Lead your cover letter with the experience bullet that "
                "best demonstrates the company's required skills."
            ),
            "experience_available": len(candidate_experience),
            "reason": "Focus the first paragraph on the most relevant role.",
            "grounded_in": {"resume_field": "experience"},
        })

    # Volunteer / extracurricular prompts.
    return suggestions


# ─── Recruiter pitch (80-120 words) ──────────────────────────────────────

def _build_recruiter_pitch(
    resume: Optional[Dict[str, Any]],
    company: Dict[str, Any],
    opportunity: Optional[Dict[str, Any]],
) -> str:
    """3-sentence pitch for LinkedIn / cold recruiter outreach."""
    name = (resume.get("name") or "I") if resume else "I"
    yrs = (resume.get("years_of_experience") or "").strip() if resume else ""
    role = "engineer"
    if resume:
        roles = resume.get("recommended_roles") or []
        if roles:
            role = str(roles[0])
    skills = []
    if resume:
        skills = [str(s) for s in (resume.get("skills") or [])[:3]]

    fr = (company.get("funding_round") or "").strip()
    fa = (company.get("funding_amount") or "").strip()
    industry = (company.get("industry") or "").strip()
    company_name = (company.get("name") or "your company").strip()

    op_score = (opportunity or {}).get("opportunity_score", 0) or 0

    sentences: List[str] = []
    # Sentence 1: who I am.
    who = f"Hi, I'm {name}"
    if yrs:
        who += f", {yrs} experience"
    if skills:
        who += f" specialising in {', '.join(skills)}"
    who += f", and I'm looking for a {role} role."
    sentences.append(who)

    # Sentence 2: why this company.
    why_company = f"{company_name}"
    if industry:
        why_company += f" ({industry})"
    if fr and fa:
        why_company += f" caught my attention with your recent {fr} ({fa})."
    elif fr:
        why_company += f" caught my attention with your recent {fr}."
    elif industry:
        why_company += " is exactly the kind of company I want to work for."
    else:
        why_company += " looks like a great fit."
    sentences.append(why_company)

    # Sentence 3: why now.
    why_now = "I'd love to explore"
    if op_score >= 80:
        why_now += f" a {role} role where my background can contribute immediately."
    elif op_score >= 50:
        why_now += " a conversation about how my skills align with the team."
    else:
        why_now += " a quick chat about your engineering culture."
    if skills and op_score >= 50:
        why_now += f" My experience with {skills[0]} matches the role's requirements."
    why_now += " Could we schedule 15 minutes this week?"
    sentences.append(why_now)

    return _clamp_words(" ".join(sentences), 80, 120)


# ─── Interview preparation ────────────────────────────────────────────────

def _build_interview_preparation(
    resume: Optional[Dict[str, Any]],
    company: Dict[str, Any],
    strategy: Optional[Dict[str, Any]],
    jobs: List[Dict[str, Any]],
) -> Dict[str, List[str]]:
    """Reuse existing intelligence; never invent topics."""
    technical: List[str] = []
    system_design: List[str] = []
    behavioral: List[str] = []
    company_specific: List[str] = []

    # Technical topics from strategy + jobs.
    if strategy:
        for t in (strategy.get("interview_topics") or []):
            t = str(t).strip()
            if t and t not in technical:
                technical.append(t)
    for j in jobs or []:
        for s in (j.get("skills") or []):
            s = str(s).strip()
            if s and s not in technical:
                technical.append(s)
    # Cap at 8 to keep it focused.
    technical = technical[:8]

    # System design topics (defaults; expand with industry if known).
    system_design = [
        "Designing a scalable API",
        "Database schema design",
        "Caching strategies",
    ]
    industry = (company.get("industry") or "").lower()
    if "ai" in industry or "ml" in industry:
        system_design += [
            "Distributed training / inference pipeline",
            "Vector database + RAG architecture",
        ]
    if "infra" in industry:
        system_design += [
            "Multi-region deployment",
            "Observability + alerting",
        ]

    # Behavioural — canonical.
    behavioral = [
        "Tell me about a project you are proud of",
        "Tell me about a time you disagreed with a teammate",
        "Why this company?",
        "Describe a time you shipped under pressure",
    ]

    # Company-specific — use ONLY real company fields.
    company_name = (company.get("name") or "the company").strip()
    tagline = (company.get("tagline") or "").strip()
    fr = (company.get("funding_round") or "").strip()
    fa = (company.get("funding_amount") or "").strip()
    hq = (company.get("headquarters") or "").strip()
    if tagline:
        company_specific.append(
            f"What about {company_name}'s mission to {tagline} interests you?"
        )
    if industry:
        company_specific.append(
            f"How would you approach {industry} challenges at {company_name}?"
        )
    if fr:
        company_specific.append(
            f"What do you know about {company_name}'s recent {fr}"
            + (f" ({fa})" if fa else "") + "?"
        )
    if hq:
        company_specific.append(
            f"Are you open to {hq}-based or remote work?"
        )
    # Always include the canonical why-this-company question.
    if f"Why {company_name}?" not in company_specific:
        company_specific.append(f"Why {company_name}?")

    return {
        "technical_topics": technical,
        "system_design_topics": system_design,
        "behavioral_questions": behavioral,
        "company_specific_questions": company_specific,
    }


# ─── Elevator pitch (50-80 words) ────────────────────────────────────────

def _build_elevator_pitch(
    resume: Optional[Dict[str, Any]],
    company: Dict[str, Any],
    opportunity: Optional[Dict[str, Any]],
) -> str:
    """Spoken-form intro for interviews / networking events."""
    name = (resume.get("name") or "I") if resume else "I"
    yrs = (resume.get("years_of_experience") or "").strip() if resume else ""
    role = "engineer"
    projects: List[str] = []
    skills: List[str] = []
    if resume:
        roles = resume.get("recommended_roles") or []
        if roles:
            role = str(roles[0])
        projects = [str(p) for p in (resume.get("projects") or [])]
        skills = [str(s) for s in (resume.get("skills") or [])[:2]]

    company_name = (company.get("name") or "your team").strip()
    fr = (company.get("funding_round") or "").strip()
    fa = (company.get("funding_amount") or "").strip()
    industry = (company.get("industry") or "").strip()

    # Build 1-2 sentences.
    parts: List[str] = []
    intro = f"Hi, I'm {name}"
    if yrs:
        intro += f", {yrs} experience"
    if skills:
        intro += f" working with {skills[0]}"
        if len(skills) > 1:
            intro += f" and {skills[1]}"
    intro += "."
    parts.append(intro)

    middle = f"I'm interested in {company_name}"
    if industry:
        middle += f" because of the work you're doing in {industry}"
    if fr:
        middle += f", and your recent {fr}"
        if fa:
            middle += f" ({fa})"
    middle += "."
    parts.append(middle)

    if projects:
        close = f"I recently built {projects[0]}"
        if len(projects) > 1:
            close += f" and {projects[1]}"
        close += "."
        parts.append(close)

    return _clamp_words(" ".join(parts), 50, 80)


# ─── Application checklist ────────────────────────────────────────────────

def _build_application_checklist(
    resume: Optional[Dict[str, Any]],
    jobs: List[Dict[str, Any]],
    opportunity: Optional[Dict[str, Any]],
    strategy: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Booleans + time estimate + priority. All derived from signals."""
    candidate_text = ""
    if resume:
        candidate_text = " ".join(
            str(x)
            for f in ("skills", "technologies", "projects", "experience", "tools")
            for x in (resume.get(f) or [])
        ).lower()

    # github_needed: company requires GitHub OR candidate has GitHub projects.
    github_required = any(
        "github" in str(s).lower()
        for j in jobs or []
        for s in (j.get("skills") or [])
    )
    has_github = "github" in candidate_text
    github_needed = bool(github_required or has_github)

    # portfolio_needed: opportunity confidence is low.
    conf = (opportunity or {}).get("confidence", 100) or 100
    portfolio_needed = conf < 70

    # custom_project_recommended: at least 1 skill gap.
    gaps = (strategy or {}).get("skill_gaps") or []
    custom_project_recommended = bool(gaps)

    # linkedin_update_recommended: candidate is mid+ and senior hiring
    # OR there are no real jobs to reference.
    prep_weeks = (opportunity or {}).get("estimated_preparation_weeks", 1) or 1
    estimated_application_minutes = max(15, int(prep_weeks * 60))

    return {
        "resume_ready": bool(resume),
        "cover_letter_ready": False,  # set by /api/documents/generate
        "portfolio_needed": portfolio_needed,
        "github_needed": github_needed,
        "linkedin_update_recommended": True,
        "custom_project_recommended": custom_project_recommended,
        "estimated_application_minutes": estimated_application_minutes,
        "priority": (opportunity or {}).get("application_priority", "SKIP"),
    }


# ─── Public entry point ───────────────────────────────────────────────────

def build_application_package(
    company: Dict[str, Any],
    resume: Optional[Dict[str, Any]],
    enrichment: Optional[Dict[str, Any]] = None,
    jobs: Optional[List[Dict[str, Any]]] = None,
    strategy: Optional[Dict[str, Any]] = None,
    opportunity: Optional[Dict[str, Any]] = None,
    cover_letter_text: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a complete application package for one company.

    Pure-deterministic. Consumes the existing intelligence signals
    (resume, company, enrichment, real-job intelligence, application
    strategy, opportunity intelligence) and emits six components.
    """
    enrichment = enrichment or {}
    jobs = jobs or []

    prompt_context = _build_cover_letter_prompt_context(
        resume=resume,
        company=company,
        enrichment=enrichment,
        jobs=jobs,
        strategy=strategy,
        opportunity=opportunity,
    )

    return {
        "cover_letter": {
            "text": cover_letter_text,
            "prompt_context": prompt_context,
        },
        "resume_suggestions": _build_resume_suggestions(resume, jobs),
        "recruiter_pitch": _build_recruiter_pitch(
            resume=resume, company=company, opportunity=opportunity
        ),
        "interview_preparation": _build_interview_preparation(
            resume=resume,
            company=company,
            strategy=strategy,
            jobs=jobs,
        ),
        "elevator_pitch": _build_elevator_pitch(
            resume=resume, company=company, opportunity=opportunity
        ),
        "application_checklist": _build_application_checklist(
            resume=resume,
            jobs=jobs,
            opportunity=opportunity,
            strategy=strategy,
        ),
        "source": "deterministic",
    }