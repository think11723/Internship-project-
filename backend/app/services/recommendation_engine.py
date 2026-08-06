"""Sprint 11 — Recommendation Intelligence Engine.

A pure-deterministic decision engine that turns (company + resume +
enrichment + real jobs + existing scores) into a single, personalised
recommendation with 12+ structured fields. The strategy decision
itself is rule-based — no LLM call, no randomness, no heuristics that
can't be documented.

LLMs (via the existing AIGateway) may only polish the final
natural-language strings. They never choose the strategy or compute
any numeric score.

This module is purely additive. ``career_intelligence.generate_recommendation``
merges its output into the existing recommendation dict; no key is
removed or renamed.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("fundflow.recommendation_engine")


# ─── Decision matrix ────────────────────────────────────────────────────

# Strategies in priority order. The decision engine picks the highest
# strategy whose score threshold is satisfied (with strategy-specific
# override rules for "missing" inputs). The thresholds below are the
# exact point at which the recommendation engine promotes a strategy to
# the next one.
STRATEGY_THRESHOLDS = (
    ("Apply Immediately",            80),
    ("Apply This Week",               65),
    ("Connect on LinkedIn First",     55),
    ("Cold Email Founder",            45),
    ("Monitor Hiring",                35),
    ("Wait Until Next Funding Round", 25),
    ("Build Missing Skills First",    18),
    ("Gain More Experience",          12),
    ("Track Future Openings",          6),
    ("Not Recommended",                0),
)


# ─── Scoring algorithm ──────────────────────────────────────────────────

def _candidate_years(resume: Optional[Dict[str, Any]]) -> Optional[int]:
    if not resume:
        return None
    raw = resume.get("years_of_experience") or ""
    import re
    m = re.search(r"(\d+)", str(raw))
    return int(m.group(1)) if m else None


def _company_size_bracket(size: str) -> str:
    return (size or "").strip()


def _funding_round_class(fr: str) -> str:
    """Bucket funding round into broad classes for scoring."""
    f = (fr or "").lower()
    if "pre-seed" in f or "preseed" in f:
        return "pre_seed"
    if "seed" in f:
        return "seed"
    if "series a" in f:
        return "series_a"
    if "series b" in f:
        return "series_b"
    if "series c" in f:
        return "series_c"
    if "series d" in f or "series e" in f or "series f" in f:
        return "late"
    return "unknown"


def _compute_base_score(
    resume: Optional[Dict[str, Any]],
    enrichment: Dict[str, Any],
    scores: Dict[str, int],
    jobs: List[Dict[str, Any]],
) -> int:
    """Deterministic 0-100 score from real signals.

    Documented signal weights:
      - resume fit (overall_fit / tech_fit)  : 0-40
      - hiring activity                       : 0-20 (negative if not hiring)
      - funding recency                       : 0-10
      - skill gap penalty                     : 0 to -15
      - work-mode alignment                   : 0 to 3
      - visa compatibility                    : 0 to 3 (negative if not supported)
      - interview difficulty                 : -3 to 0
    """
    score = 0

    # 1. Resume fit (max 40)
    tech_fit = scores.get("technical_fit") or 0
    overall = scores.get("overall_fit") or 0
    score += int(round((max(tech_fit, overall) * 0.4)))

    # 2. Hiring activity (max 20, min -15)
    status = (enrichment.get("hiring_status_detailed") or "").strip()
    open_count = int(enrichment.get("open_positions_count") or 0)
    if status == "actively_hiring":
        if open_count >= 3:
            score += 20
        elif open_count >= 1:
            score += 15
        else:
            score += 12
    elif status == "hiring":
        score += 8
    elif status == "not_hiring":
        score -= 15
    # unknown -> 0

    # 3. Funding recency (max 10)
    fr = _funding_round_class(enrichment.get("funding_round") or "")
    score += {
        "pre_seed": 6, "seed": 9, "series_a": 10,
        "series_b": 8, "series_c": 6, "late": 4,
        "unknown": 0,
    }.get(fr, 0)

    # 4. Skill gap penalty (max 0, min -15)
    candidate_skills = set()
    if resume:
        for f in ("skills", "technologies", "programming_languages",
                  "frameworks", "cloud", "databases", "tools"):
            for s in (resume.get(f) or []):
                v = (s or "").strip().lower()
                if v:
                    candidate_skills.add(v)
    required = set()
    for j in jobs or []:
        for s in (j.get("skills") or []):
            v = (s or "").strip().lower()
            if v:
                required.add(v)
    if required:
        missing = len(required - candidate_skills)
        if missing >= 7:
            score -= 15
        elif missing >= 5:
            score -= 10
        elif missing >= 3:
            score -= 5
        # 0-2 missing: no penalty

    # 5. Work mode (max 3)
    wm = (enrichment.get("work_mode") or "").strip().lower()
    if wm == "remote":
        score += 3
    elif wm == "hybrid":
        score += 1
    # onsite / unknown: 0

    # 6. Visa compatibility (max 3, min -10)
    visa = enrichment.get("visa_sponsorship_mentioned")
    if visa is True:
        score += 3
    elif visa is False:
        score -= 10

    # 7. Interview difficulty (-3 to 0)
    diff = (enrichment.get("preferred_experience_level") or "").lower()
    if diff in ("senior", "principal", "staff"):
        yrs = _candidate_years(resume)
        if yrs is not None and yrs < 5:
            score -= 3
    # mid / unknown / junior: no penalty

    return max(0, min(100, score))


# ─── Strategy override rules ────────────────────────────────────────────

def _strategy_overrides(
    resume: Optional[Dict[str, Any]],
    enrichment: Dict[str, Any],
    jobs: List[Dict[str, Any]],
    candidate_skills: set,
) -> Optional[str]:
    """Force a specific strategy when the rules demand it.

    Returns None if the score-based strategy should be used; returns
    a strategy string if an override is required.
    """
    # No resume -> Not Recommended
    if resume is None:
        return "Not Recommended"

    status = (enrichment.get("hiring_status_detailed") or "").strip()
    open_count = int(enrichment.get("open_positions_detailed") or enrichment.get("open_positions_count") or 0)

    # 5+ skill gaps and mid/junior -> Build Missing Skills First
    yrs = _candidate_years(resume)
    required = set()
    for j in jobs or []:
        for s in (j.get("skills") or []):
            v = (s or "").strip().lower()
            if v:
                required.add(v)
    missing = len(required - candidate_skills) if required else 0
    if missing >= 6 and (yrs is None or yrs <= 5):
        return "Build Missing Skills First"

    # Senior role + junior candidate -> Gain More Experience
    pref = (enrichment.get("preferred_experience_level") or "").lower()
    if pref in ("senior", "principal", "staff") and yrs is not None and yrs < 3:
        return "Gain More Experience"

    # Visa not supported AND onsite -> Monitor Hiring
    visa = enrichment.get("visa_sponsorship_mentioned")
    wm = (enrichment.get("work_mode") or "").strip().lower()
    if visa is False and wm == "onsite":
        return "Monitor Hiring"

    # Not hiring at all
    if status == "not_hiring":
        # But if the company is freshly funded and has no jobs yet,
        # track future openings rather than "monitor hiring".
        fr = _funding_round_class(enrichment.get("funding_round") or "")
        if fr in ("pre_seed", "seed") and open_count == 0:
            return "Track Future Openings"
        return "Monitor Hiring"

    return None


# ─── Main strategy selector ──────────────────────────────────────────────

def select_strategy(
    base_score: int,
    override: Optional[str],
) -> str:
    if override is not None:
        return override
    for name, threshold in STRATEGY_THRESHOLDS:
        if base_score >= threshold:
            return name
    return "Not Recommended"


def _priority_for(strategy: str) -> str:
    high = {
        "Apply Immediately",
    }
    medium = {
        "Apply This Week",
        "Connect on LinkedIn First",
        "Cold Email Founder",
    }
    if strategy in high:
        return "HIGH"
    if strategy in medium:
        return "MEDIUM"
    if strategy in (
        "Monitor Hiring", "Wait Until Next Funding Round",
        "Build Missing Skills First", "Gain More Experience",
    ):
        return "LOW"
    return "SKIP"


# ─── Probability / difficulty estimators (all deterministic) ──────────

def _resume_pass_probability(
    tech_fit: int, candidate_years: Optional[int],
    exp_level: str, gaps: int,
) -> int:
    base = max(0, min(100, tech_fit))
    if exp_level in ("senior", "principal", "staff"):
        if candidate_years is not None and candidate_years >= 7:
            base += 5
        elif candidate_years is not None and candidate_years < 3:
            base -= 15
    elif exp_level == "mid":
        if candidate_years is not None and 2 <= candidate_years <= 6:
            base += 5
    base -= min(20, gaps * 2)
    return max(5, min(95, base))


def _interview_probability(
    resume_pass: int, competition: str, difficulty: str,
) -> int:
    base = int(resume_pass * 0.7)
    if competition == "low":
        base += 10
    elif competition == "high":
        base -= 15
    if difficulty == "Easy":
        base += 8
    elif difficulty == "Hard":
        base -= 12
    elif difficulty == "Very Hard":
        base -= 20
    return max(3, min(80, base))


def _response_probability(
    company_size: str, open_positions: int,
) -> int:
    s = (company_size or "").strip()
    if any(x in s for x in ("1,001-5,000", "5,001-10,000", "10,001+")):
        base = 25
    elif any(x in s for x in ("201-500", "501-1,000")):
        base = 40
    elif any(x in s for x in ("51-200",)):
        base = 50
    elif any(x in s for x in ("11-50",)):
        base = 65
    elif "1-10" in s or s.strip() == "":
        base = 75
    else:
        base = 50
    base += min(15, int(open_positions or 0) * 2)
    return max(5, min(90, base))


def _application_difficulty(
    gaps: int, visa: Any, exp_level: str, candidate_years: Optional[int],
) -> str:
    score = 30  # baseline
    score += min(25, gaps * 3)
    if visa is False:
        score += 15
    if exp_level in ("senior", "principal", "staff"):
        if candidate_years is not None and candidate_years < 5:
            score += 20
    elif exp_level in ("junior", "entry level", "entry-level", "new grad"):
        if candidate_years is not None and candidate_years > 4:
            score += 10
    if score < 25:
        return "Easy"
    if score < 55:
        return "Medium"
    if score < 80:
        return "Hard"
    return "Very Hard"


def _competition_level(
    company_size: str, industry: str, open_positions: int,
) -> str:
    s = (company_size or "").strip()
    if any(x in s for x in ("10,001+",)):
        base = "high"
    elif any(x in s for x in ("5,001-10,000",)):
        base = "high"
    elif any(x in s for x in ("1,001-5,000",)):
        base = "high"
    elif any(x in s for x in ("501-1,000",)):
        base = "medium"
    elif any(x in s for x in ("201-500",)):
        base = "medium"
    elif any(x in s for x in ("51-200",)):
        base = "low"
    elif any(x in s for x in ("11-50",)):
        base = "low"
    elif "1-10" in s or s == "":
        base = "low"
    else:
        base = "medium"
    ind = (industry or "").lower()
    if "ai" in ind or "machine learning" in ind or "llm" in ind:
        if base == "low":
            base = "medium"
        elif base == "medium":
            base = "high"
    if open_positions >= 5 and base == "low":
        base = "medium"
    return base


def _expected_hiring_speed(
    funding_round: str, open_positions: int, recent_hiring: bool,
) -> str:
    if open_positions <= 0 and not recent_hiring:
        return "Slow (1+ month)"
    if open_positions >= 5 and recent_hiring:
        return "Fast (1-2 weeks)"
    if open_positions >= 1 and recent_hiring:
        return "Medium (2-4 weeks)"
    if recent_hiring:
        return "Medium (2-4 weeks)"
    return "Slow (1+ month)"


def _recommended_window(strategy: str) -> str:
    return {
        "Apply Immediately": "Within 24 hours",
        "Apply This Week": "Within 7 days",
        "Connect on LinkedIn First": "Within 2 weeks",
        "Cold Email Founder": "Within 1 week",
        "Monitor Hiring": "Ongoing (re-check every 2 weeks)",
        "Wait Until Next Funding Round": "Wait 3-6 months for next round",
        "Build Missing Skills First": "Wait 1-3 months while building skills",
        "Gain More Experience": "Wait 1-2 years for senior readiness",
        "Track Future Openings": "Ongoing (subscribe to careers page)",
        "Not Recommended": "Not applicable",
    }.get(strategy, "Unknown")


# ─── Reasoning builder (always evidence-grounded) ──────────────────────

def _build_reasoning(
    resume: Optional[Dict[str, Any]],
    enrichment: Dict[str, Any],
    jobs: List[Dict[str, Any]],
    candidate_skills: set,
    strategy: str,
    score: int,
) -> List[str]:
    """Produce 3-5 reason bullets. Every bullet cites a real signal."""
    reasons: List[str] = []
    fr = (enrichment.get("funding_round") or "").strip()
    fa = (enrichment.get("funding_amount") or "").strip()
    if fr and fa:
        reasons.append(f"Funding: {fr} ({fa})")
    elif fr:
        reasons.append(f"Funding: {fr}")
    else:
        reasons.append("Funding stage undisclosed")

    status = (enrichment.get("hiring_status_detailed") or "").strip()
    open_count = int(enrichment.get("open_positions_count") or 0)
    eng_roles = int(
        (enrichment.get("hiring_summary") or {}).get("engineering_roles") or 0
    )
    if status == "actively_hiring":
        if eng_roles and open_count:
            reasons.append(
                f"Actively hiring ({open_count} open roles, {eng_roles} engineering)"
            )
        elif open_count:
            reasons.append(f"Actively hiring ({open_count} open roles)")
        else:
            reasons.append("Actively hiring (number of roles undisclosed)")
    elif status == "hiring":
        reasons.append("Currently hiring (slow pace)")
    elif status == "not_hiring":
        reasons.append("Not currently hiring (must wait or watch)")
    else:
        reasons.append("Hiring status undisclosed")

    company_skills = set()
    for j in jobs or []:
        for s in (j.get("skills") or []):
            v = (s or "").strip().lower()
            if v:
                company_skills.add(v)
    overlap = company_skills & candidate_skills
    missing = company_skills - candidate_skills
    if company_skills:
        if overlap:
            overlap_sample = ", ".join(sorted(overlap)[:3])
            reasons.append(
                f"Skill match: {len(overlap)}/{len(company_skills)} "
                f"(overlap: {overlap_sample})"
            )
        else:
            reasons.append(
                f"Skill match: 0/{len(company_skills)} — large gap to fill"
            )
        if missing:
            missing_sample = ", ".join(sorted(missing)[:3])
            reasons.append(
                f"Missing: {len(missing)} skills ({missing_sample})"
            )

    exp_level = (enrichment.get("preferred_experience_level") or "").strip()
    yrs = _candidate_years(resume)
    if exp_level and yrs is not None:
        if exp_level in ("senior", "principal", "staff") and yrs >= 7:
            reasons.append(
                f"Seniority match: {yrs}y experience aligns with {exp_level} role"
            )
        elif exp_level == "mid" and 2 <= yrs <= 6:
            reasons.append(
                f"Seniority match: {yrs}y experience fits {exp_level}-level role"
            )
        elif exp_level in ("senior", "principal", "staff") and yrs < 5:
            reasons.append(
                f"Seniority mismatch: {yrs}y experience for {exp_level} role"
            )

    wm = (enrichment.get("work_mode") or "").strip()
    if wm == "remote":
        reasons.append("Work mode: remote (no relocation barrier)")
    elif wm == "hybrid":
        reasons.append("Work mode: hybrid")
    elif wm == "onsite":
        reasons.append("Work mode: onsite (relocation may be required)")

    return reasons[:5]


# ─── Next actions builder ──────────────────────────────────────────────

def _build_next_actions(
    resume: Optional[Dict[str, Any]],
    enrichment: Dict[str, Any],
    jobs: List[Dict[str, Any]],
    candidate_skills: set,
    strategy: str,
    gaps: int,
) -> List[str]:
    actions: List[str] = []
    if strategy == "Apply Immediately":
        actions.append("Submit application today via careers page")
        actions.append("Send a brief LinkedIn message to the hiring manager")
        if gaps > 0:
            missing_top = sorted(
                set().union(
                    *[set(j.get("skills") or []) for j in jobs]
                ) - candidate_skills
            )[:3]
            for s in missing_top:
                actions.append(f"Re-frame existing {s} experience in cover letter")
        actions.append("Set up a calendar reminder to follow up in 1 week")
    elif strategy == "Apply This Week":
        actions.append("Tailor resume summary to the role's required skills")
        if gaps > 0:
            missing_top = sorted(
                set().union(
                    *[set(j.get("skills") or []) for j in jobs]
                ) - candidate_skills
            )[:3]
            for s in missing_top:
                actions.append(f"Address gap: add a short {s} note to your resume")
        actions.append("Apply through the careers page by end of week")
        actions.append("Connect with one engineer at the company on LinkedIn")
    elif strategy == "Connect on LinkedIn First":
        actions.append("Identify 2-3 employees at the company on LinkedIn")
        actions.append("Send a 3-sentence connection request mentioning a project")
        actions.append("Wait 5-7 days before applying; reference the intro in cover letter")
        actions.append("Apply via careers page once connection is established")
    elif strategy == "Cold Email Founder":
        actions.append("Find the founder's email (Hunter.io, about page, or personal site)")
        actions.append("Send a 5-sentence email with a specific, useful observation about their work")
        actions.append("Attach a one-page portfolio or relevant GitHub link")
        actions.append("Follow up once after 4-5 days, then move on")
    elif strategy == "Monitor Hiring":
        actions.append("Subscribe to the careers page for change notifications")
        actions.append("Re-check every 2 weeks; set a calendar reminder")
        actions.append("Build 1 small project in their tech stack to be ready when hiring resumes")
    elif strategy == "Wait Until Next Funding Round":
        actions.append("Set a Google Alert for company funding announcements")
        actions.append("Re-evaluate in 3-6 months when next round is likely")
        actions.append("Maintain visibility by occasionally engaging with their content")
    elif strategy == "Build Missing Skills First":
        actions.append(f"Build 1 small project covering top missing skills")
        actions.append(f"Document it on GitHub with a clear README")
        actions.append(f"Re-apply in 1-3 months when portfolio is ready")
    elif strategy == "Gain More Experience":
        actions.append("Take a stretch assignment in your current role")
        actions.append("Build a senior-level side project in your spare time")
        actions.append("Re-evaluate readiness in 1-2 years")
    elif strategy == "Track Future Openings":
        actions.append("Subscribe to the company's careers page")
        actions.append("Set a quarterly calendar reminder to re-check")
        actions.append("Engage with their content on social media for visibility")
    else:  # Not Recommended
        actions.append("Skip this opportunity for now")
        actions.append("Focus on opportunities that match your profile more closely")

    # Always add a final generic action
    actions.append("Save this analysis for future reference")

    return actions[:7]


# ─── Public entry point ─────────────────────────────────────────────────

def _candidate_skill_set(resume: Optional[Dict[str, Any]]) -> set:
    if not resume:
        return set()
    out: set = set()
    for f in ("skills", "technologies", "programming_languages",
              "frameworks", "cloud", "databases", "tools"):
        for s in (resume.get(f) or []):
            v = (s or "").strip().lower()
            if v:
                out.add(v)
    return out


def _recent_hiring(enrichment: Dict[str, Any]) -> bool:
    """True if the company is actively hiring AND has at least one role."""
    s = (enrichment.get("hiring_status_detailed") or "").strip()
    if s != "actively_hiring":
        return False
    return int(enrichment.get("open_positions_count") or 0) > 0


def build_recommendation_intelligence(
    company: Dict[str, Any],
    resume: Optional[Dict[str, Any]],
    enrichment: Optional[Dict[str, Any]] = None,
    jobs: Optional[List[Dict[str, Any]]] = None,
    scores: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """Build a deterministic per-company recommendation intelligence dict.

    The returned dict has these top-level keys (all required by spec):
      - strategy                    (str)
      - confidence                  (int 0-100)
      - priority                    ("HIGH" | "MEDIUM" | "LOW" | "SKIP")
      - reasoning                   (List[str] of 3-5 evidence-grounded bullets)
      - next_actions                (List[str] checklist)
      - estimated_resume_pass_probability   (int 0-100)
      - estimated_interview_probability     (int 0-100)
      - estimated_response_probability      (int 0-100)
      - application_difficulty      ("Easy" | "Medium" | "Hard" | "Very Hard")
      - competition_level           ("low" | "medium" | "high")
      - expected_hiring_speed       (str)
      - recommended_application_window (str)
    """
    enrichment = enrichment or {}
    jobs = jobs or []
    scores = scores or {}

    candidate_skills = _candidate_skill_set(resume)

    # Compute the base score (deterministic)
    base = _compute_base_score(resume, enrichment, scores, jobs)

    # Apply strategy overrides
    override = _strategy_overrides(resume, enrichment, jobs, candidate_skills)
    strategy = select_strategy(base, override)

    # Build the response probabilities
    tech_fit = int(scores.get("technical_fit") or 0)
    exp_level = (enrichment.get("preferred_experience_level") or "").strip()
    yrs = _candidate_years(resume)

    # Compute gap count
    required = set()
    for j in jobs or []:
        for s in (j.get("skills") or []):
            v = (s or "").strip().lower()
            if v:
                required.add(v)
    gaps = len(required - candidate_skills) if required else 0

    company_size = _company_size_bracket(
        enrichment.get("employee_count_bracket") or ""
    )
    industry = (enrichment.get("primary_ai_domain") or company.get("industry") or "").strip()
    open_count = int(enrichment.get("open_positions_count") or 0)
    recent = _recent_hiring(enrichment)

    resume_pass = _resume_pass_probability(tech_fit, yrs, exp_level, gaps)
    competition = _competition_level(company_size, industry, open_count)
    diff = _application_difficulty(gaps, enrichment.get("visa_sponsorship_mentioned"),
                                  exp_level, yrs)
    interview_prob = _interview_probability(resume_pass, competition, diff)
    response_prob = _response_probability(company_size, open_count)
    hiring_speed = _expected_hiring_speed(
        enrichment.get("funding_round") or "", open_count, recent
    )
    window = _recommended_window(strategy)

    # Confidence = score + boost for data completeness
    confidence = base
    if resume is not None:
        confidence += 10
    if scores.get("technical_fit", 0) > 0:
        confidence += 5
    if enrichment.get("hiring_status_detailed"):
        confidence += 5
    if open_count > 0:
        confidence += 5
    if enrichment.get("funding_round"):
        confidence += 3
    confidence = max(0, min(100, confidence))

    priority = _priority_for(strategy)

    reasoning = _build_reasoning(
        resume, enrichment, jobs, candidate_skills, strategy, base
    )
    next_actions = _build_next_actions(
        resume, enrichment, jobs, candidate_skills, strategy, gaps
    )

    return {
        "strategy": strategy,
        "confidence": confidence,
        "priority": priority,
        "reasoning": reasoning,
        "next_actions": next_actions,
        "estimated_resume_pass_probability": resume_pass,
        "estimated_interview_probability": interview_prob,
        "estimated_response_probability": response_prob,
        "application_difficulty": diff,
        "competition_level": competition,
        "expected_hiring_speed": hiring_speed,
        "recommended_application_window": window,
    }
