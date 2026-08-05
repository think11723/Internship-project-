"""Sprint 7 — Opportunity Intelligence.

Adds an explainable ``Opportunity Score`` for every company. Built
entirely from signals already collected by the discovery pipeline
(Sprints 1-3), the application strategy engine (Sprint 5), and the
real-job intelligence parser (Sprint 6). No new APIs, no new
scraping, no LLM calls.

Every point on the score is derived from evidence. Every "why
apply now" bullet is grounded in a specific signal value. The score
breakdown is returned so the candidate can audit it.

Additive. Sprint 7's ``compute_opportunity_intelligence`` is invoked
from ``application_strategy.build_application_strategy``, which
merges the returned fields into the existing recommendation dict
(``opportunity`` sub-dict, additive — no existing keys removed).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


# ─── Star rating thresholds ────────────────────────────────────────────────

_STAR_THRESHOLDS = (
    (90, "★★★★★", "Excellent opportunity"),
    (75, "★★★★",  "Strong opportunity"),
    (60, "★★★",   "Good opportunity"),
    (40, "★★",    "Moderate — proceed with caution"),
    (20, "★",     "Weak — skip"),
    (0,  "✕",     "Not worth applying now"),
)


def _star_rating(score: int) -> str:
    for threshold, stars, _ in _STAR_THRESHOLDS:
        if score >= threshold:
            return stars
    return "✕"


def _label_for_score(score: int) -> str:
    for threshold, _, label in _STAR_THRESHOLDS:
        if score >= threshold:
            return label
    return "Not worth applying now"


def _priority_for_score(score: int) -> str:
    if score >= 80:
        return "HIGH"
    if score >= 60:
        return "MEDIUM"
    if score >= 40:
        return "LOW"
    return "SKIP"


# ─── Signal extraction ────────────────────────────────────────────────────

def _safe_int(x, default: int = 0) -> int:
    try:
        return int(x)
    except (TypeError, ValueError):
        return default


def _candidate_years(resume: Optional[Dict[str, Any]]) -> Optional[int]:
    """Extract candidate's years of experience from the resume."""
    if not resume:
        return None
    raw = resume.get("years_of_experience")
    if not raw:
        return None
    m = __import__("re").search(r"(\d+)", str(raw))
    return int(m.group(1)) if m else None


def _is_junior_candidate(resume: Optional[Dict[str, Any]]) -> bool:
    yrs = _candidate_years(resume)
    return yrs is not None and yrs <= 2


def _is_senior_candidate(resume: Optional[Dict[str, Any]]) -> bool:
    yrs = _candidate_years(resume)
    return yrs is not None and yrs >= 7


def _gaps_count(strategy: Optional[Dict[str, Any]]) -> int:
    if not strategy:
        return 0
    return len(strategy.get("skill_gaps") or [])


def _estimate_preparation_weeks(
    gaps: int, difficulty: str
) -> int:
    """Weeks of preparation based on gap count + interview difficulty."""
    base = 1 if gaps <= 1 else (2 if gaps <= 2 else (3 if gaps <= 3 else (4 if gaps <= 5 else 6)))
    if difficulty == "Hard":
        base += 2
    elif difficulty == "Easy":
        base = max(1, base - 1)
    return max(1, base)


def _interview_probability(
    overall_fit: int, confidence: int
) -> str:
    if confidence >= 80 and overall_fit >= 70:
        return "High"
    if confidence >= 50 and overall_fit >= 50:
        return "Medium"
    if overall_fit < 30 or confidence < 50:
        return "Very Low"
    return "Low"


def _resume_strength(overall_fit: int) -> str:
    if overall_fit >= 80:
        return "Strong"
    if overall_fit >= 65:
        return "Good"
    if overall_fit >= 50:
        return "Moderate"
    if overall_fit >= 35:
        return "Weak"
    return "Very Weak"


def _effort_estimate(gaps: int, difficulty: str) -> str:
    if difficulty == "Hard" or gaps >= 3:
        return "High"
    if gaps <= 1 and difficulty in ("Easy", "Medium"):
        return "Low"
    return "Moderate"


# ─── Score breakdown ────────────────────────────────────────────────────────

def _score_resume_match(scores: Dict[str, int]) -> tuple:
    """Resume fit: linear scale, 0..40 points."""
    overall = max(0, min(100, int(scores.get("overall_fit", 0) or 0)))
    pts = int(round(overall * 0.4))
    return pts, f"Resume match (overall_fit={overall})"


def _score_hiring(enrichment: Dict[str, Any]) -> tuple:
    """Hiring signal: -10..+20 points."""
    status = (enrichment.get("hiring_status_detailed") or "").strip()
    open_count = _safe_int(enrichment.get("open_positions_count"), 0)
    if status == "actively_hiring":
        if open_count >= 3:
            return 20, f"Actively hiring ({open_count} open roles)"
        if open_count >= 1:
            return 15, f"Actively hiring ({open_count} open role"
        return 12, "Actively hiring"
    if status == "hiring":
        return 8, "Currently hiring"
    if status == "not_hiring":
        return -10, "Not currently hiring"
    return 0, "Hiring status unknown"


def _score_skill_gap(gaps: int, strategy: Optional[Dict[str, Any]]) -> tuple:
    """Skill gap: 0..15 points (or -5 for PhD-only signals)."""
    if gaps == 0:
        return 15, "Zero skill gaps"
    if gaps <= 2:
        return 10, f"Small skill gap ({gaps} skills)"
    if gaps <= 4:
        return 5, f"Moderate skill gap ({gaps} skills)"
    if gaps <= 6:
        return 0, f"Large skill gap ({gaps} skills)"
    return -5, f"Very large skill gap ({gaps} skills)"


def _score_funding_stage(
    company: Dict[str, Any], enrichment: Dict[str, Any]
) -> tuple:
    """Recent funding: 0..10 points. Sweet spot: Series A-C + small team."""
    fr = (company.get("funding_round") or "").lower()
    if not fr:
        return 0, "Funding stage not disclosed"
    size = (enrichment.get("employee_count_bracket") or "").strip()
    big = "200" in size or "500" in size or "1,000" in size or "5,000" in size or "10,001" in size

    if "seed" in fr or "pre-seed" in fr:
        return 6, f"Seed stage ({company.get('funding_round')})"
    if "series a" in fr:
        return 10 if not big else 7, f"Series A funding"
    if "series b" in fr:
        return 9 if not big else 6, f"Series B funding"
    if "series c" in fr:
        return 7 if not big else 4, f"Series C funding"
    if "series d" in fr or "series e" in fr or "series f" in fr:
        return 5 if not big else 3, f"Late-stage ({company.get('funding_round')})"
    return 4, f"Funding stage: {company.get('funding_round')}"


def _score_remote(enrichment: Dict[str, Any]) -> tuple:
    mode = (enrichment.get("work_mode") or "").strip().lower()
    if mode == "remote":
        return 5, "Remote opportunity"
    if mode == "hybrid":
        return 3, "Hybrid work"
    if mode == "onsite":
        return 0, "Onsite only"
    return 0, "Work mode unknown"


def _score_visa(enrichment: Dict[str, Any]) -> tuple:
    v = enrichment.get("visa_sponsorship_mentioned")
    if v is True:
        return 5, "Visa sponsorship mentioned"
    if v is False:
        return -5, "Visa sponsorship not supported"
    return 0, "Visa status unknown"


def _score_confidence(strategy: Optional[Dict[str, Any]]) -> tuple:
    conf = (strategy or {}).get("confidence", 0) or 0
    if conf >= 80:
        return 5, f"High data confidence ({conf})"
    if conf >= 60:
        return 3, f"Moderate data confidence ({conf})"
    if conf >= 40:
        return 1, f"Low data confidence ({conf})"
    return 0, "Insufficient data"


def _score_difficulty(difficulty: str) -> tuple:
    if difficulty == "Hard":
        return -3, "Hard interview"
    if difficulty == "Medium":
        return 0, "Medium interview difficulty"
    if difficulty == "Easy":
        return 3, "Easy interview"
    return 0, "Interview difficulty unknown"


def _score_experience_match(
    resume: Optional[Dict[str, Any]],
    enrichment: Dict[str, Any]
) -> tuple:
    """Match between candidate's years and preferred experience level."""
    candidate_years = _candidate_years(resume)
    pref = (enrichment.get("preferred_experience_level") or "").lower()
    if candidate_years is None or not pref or pref == "unknown":
        return 0, "Experience level not aligned"
    if pref in ("senior", "principal", "staff"):
        if candidate_years >= 7:
            return 3, "Senior role matches candidate experience"
        if candidate_years <= 3:
            return -3, "Senior role expects more experience than candidate has"
        return -1, "Senior role slightly above candidate experience"
    if pref == "mid":
        if 2 <= candidate_years <= 6:
            return 3, "Mid-level role matches candidate experience"
        return 0, "Mid-level role acceptable"
    if pref in ("junior", "entry level", "entry-level", "new grad"):
        if candidate_years <= 3:
            return 3, "Entry-level role matches candidate experience"
        if candidate_years >= 6:
            return -3, "Entry-level role is below candidate experience"
        return 0, "Entry-level role undersells candidate"
    return 0, "Experience level not aligned"


def _score_internship_fit(
    resume: Optional[Dict[str, Any]],
    enrichment: Dict[str, Any],
    hiring_summary: Optional[Dict[str, Any]]
) -> tuple:
    """Bonus if candidate is junior + company has intern/grad roles."""
    intern_count = (hiring_summary or {}).get("internships", 0) or 0
    grad_count = (hiring_summary or {}).get("graduate_roles", 0) or 0
    if intern_count + grad_count == 0:
        return 0, "No intern/grad roles"
    if _is_junior_candidate(resume):
        return 5, f"Intern/grad roles match junior candidate ({intern_count + grad_count} available)"
    if _is_senior_candidate(resume):
        return -2, "Senior candidate with intern/grad-only openings"
    return 1, f"Intern/grad roles available ({intern_count + grad_count})"


# ─── "Why apply now" / "Reasons to skip" reasoning ────────────────────────

def _build_why_apply_now(
    company: Dict[str, Any],
    enrichment: Dict[str, Any],
    strategy: Optional[Dict[str, Any]],
    hiring_summary: Optional[Dict[str, Any]],
    score_breakdown: Dict[str, int],
) -> List[str]:
    """Up to 5 evidence-grounded reasons TO apply."""
    reasons: List[str] = []
    fr = (company.get("funding_round") or "").strip()
    fa = (company.get("funding_amount") or "").strip()
    if fr and fa:
        reasons.append(f"Fresh {fr} funding ({fa})")
    elif fr:
        reasons.append(f"Fresh {fr} funding")
    status = (enrichment.get("hiring_status_detailed") or "").strip()
    open_count = (hiring_summary or {}).get("total_roles", 0) or 0
    if status == "actively_hiring" and open_count:
        reasons.append(
            "Backend hiring active" if (hiring_summary or {}).get("engineering_roles", 0) > 0
            else f"Actively hiring ({open_count} open roles)"
        )
    elif status == "hiring":
        reasons.append("Currently hiring")
    gaps = _gaps_count(strategy)
    if gaps == 0:
        reasons.append("Resume already matches all required skills")
    elif gaps <= 2:
        reasons.append(f"Small skill gap ({gaps} skill{'s' if gaps != 1 else ''})")
    if (enrichment.get("work_mode") or "").lower() == "remote":
        reasons.append("Remote opportunity")
    if enrichment.get("visa_sponsorship_mentioned") is True:
        reasons.append("Visa sponsorship available")
    if (hiring_summary or {}).get("engineering_roles", 0) >= 3:
        reasons.append(
            f"{(hiring_summary or {}).get('engineering_roles')} engineering roles open"
        )
    return reasons[:5]


def _build_reasons_to_skip(
    company: Dict[str, Any],
    enrichment: Dict[str, Any],
    strategy: Optional[Dict[str, Any]],
    score_breakdown: Dict[str, int],
) -> List[str]:
    """Up to 5 evidence-grounded reasons to SKIP this opportunity.

    Only populated for weak opportunities.
    """
    reasons: List[str] = []
    gaps = _gaps_count(strategy)
    if gaps >= 5:
        reasons.append(f"Large skill gap ({gaps} skills to learn)")
    status = (enrichment.get("hiring_status_detailed") or "").strip()
    if status == "not_hiring":
        reasons.append("No active hiring")
    if enrichment.get("visa_sponsorship_mentioned") is False:
        reasons.append("Visa sponsorship not supported")
    pref = (enrichment.get("preferred_experience_level") or "").lower()
    candidate_years = _candidate_years((strategy or {}).get("_candidate_years"))  # always None; safe
    if pref in ("senior", "principal", "staff") and (candidate_years or 0) < 5:
        reasons.append("Senior role — requires more experience than candidate has")
    fr = (company.get("funding_round") or "").lower()
    if "research" in (company.get("industry") or "").lower() and "phd" in (strategy or {}).get("_phd_hint", ""):
        reasons.append("Research-heavy role")
    if score_breakdown.get("hiring_active", 0) <= -5:
        reasons.append("No recent hiring activity")
    if (enrichment.get("work_mode") or "").lower() == "onsite":
        reasons.append("Onsite only — no remote option")
    return reasons[:5]


# ─── Public entry point ───────────────────────────────────────────────────

def compute_opportunity_intelligence(
    company: Dict[str, Any],
    resume: Optional[Dict[str, Any]],
    strategy: Optional[Dict[str, Any]],
    enrichment: Optional[Dict[str, Any]] = None,
    hiring_summary: Optional[Dict[str, Any]] = None,
    scores: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """Compute an explainable Opportunity Assessment for one company.

    Returns a dict with:
        opportunity_score            (0..100)
        overall_opportunity          ("★★★★★" etc.)
        application_priority         ("HIGH" | "MEDIUM" | "LOW" | "SKIP")
        score_breakdown              ({signal_name: points, ...})
        why_apply_now                 (List[str], up to 5)
        reasons_to_skip               (List[str], up to 5; empty for good)
        estimated_preparation_weeks   (int)
        estimated_interview_probability  (High/Medium/Low/Very Low)
        estimated_resume_strength     (Strong/Good/Moderate/Weak/Very Weak)
        estimated_effort              (Low/Moderate/High)
    """
    enrichment = enrichment or {}
    scores = scores or {}
    strategy = strategy or {}
    hiring_summary = hiring_summary or {}

    # Score each signal. Total clamped to 0..100.
    raw_signals = [
        ("resume_match",       _score_resume_match(scores)),
        ("hiring_active",      _score_hiring(enrichment)),
        ("small_skill_gap",    _score_skill_gap(_gaps_count(strategy), strategy)),
        ("recent_funding",     _score_funding_stage(company, enrichment)),
        ("remote_available",   _score_remote(enrichment)),
        ("visa_support",       _score_visa(enrichment)),
        ("internship_fit",     _score_internship_fit(resume, enrichment, hiring_summary)),
        ("data_confidence",    _score_confidence(strategy)),
        ("interview_difficulty", _score_difficulty(
            (strategy or {}).get("estimated_interview_difficulty") or "Unknown"
        )),
        ("experience_match",   _score_experience_match(resume, enrichment)),
    ]
    breakdown: Dict[str, int] = {}
    raw_total = 0
    for name, (pts, _reason) in raw_signals:
        breakdown[name] = pts
        raw_total += pts
    score = max(0, min(100, raw_total))

    # Build reasoning.
    why_apply = _build_why_apply_now(
        company, enrichment, strategy, hiring_summary, breakdown
    )
    reasons_to_skip: List[str] = []
    # Only populate reasons-to-skip when score is weak.
    if score < 50:
        reasons_to_skip = _build_reasons_to_skip(
            company, enrichment, strategy, breakdown
        )

    # Effort / preparation / probability / resume strength.
    gaps = _gaps_count(strategy)
    difficulty = (strategy or {}).get(
        "estimated_interview_difficulty", "Unknown"
    )
    overall_fit = int(scores.get("overall_fit", 0) or 0)
    confidence = int((strategy or {}).get("confidence", 0) or 0)

    return {
        "opportunity_score": score,
        "overall_opportunity": _star_rating(score),
        "application_priority": _priority_for_score(score),
        "score_breakdown": breakdown,
        "why_apply_now": why_apply,
        "reasons_to_skip": reasons_to_skip,
        "estimated_preparation_weeks": _estimate_preparation_weeks(
            gaps, difficulty
        ),
        "estimated_interview_probability": _interview_probability(
            overall_fit, confidence
        ),
        "estimated_resume_strength": _resume_strength(overall_fit),
        "estimated_effort": _effort_estimate(gaps, difficulty),
    }