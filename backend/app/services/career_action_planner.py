"""Sprint 13 — Career Action Planner.

Consumes the (frozen) outputs of the Recommendation Engine (Sprint 11),
the Opportunity Intelligence v2 (Sprint 12), the Opportunity v1
(Sprint 7), the deterministic extractor, and the resume profile, and
produces a single, unified, deterministic Career Action Plan.

No new LLM dependencies. No new scoring engines. No modification to
any frozen infrastructure. This module composes existing signals into
concrete actions the candidate can execute today, this week, and
next.

LLMs (via the existing AIGateway) may only polish the final natural-
language strings. They never decide which actions appear.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("fundflow.career_planner")


# ─── Day-of-week ordering ────────────────────────────────────────────────

_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")


# ─── Resume-improvement generator ───────────────────────────────────────

def _resume_improvements(
    resume: Optional[Dict[str, Any]],
    real_jobs: List[Dict[str, Any]],
    top_gaps: List[str],
) -> List[str]:
    """Generate 3-5 actionable resume improvements from real signals.

    Every suggestion references either:
      - a skill the candidate already has and should highlight, OR
      - a missing skill the candidate should reframe or build, OR
      - a project already on the resume that should be reordered.

    No fabrication of skills, projects, or experience.
    """
    out: List[str] = []

    # 1. Reorder highlight of high-overlap required skills
    candidate_skills = set()
    if resume:
        for f in ("skills", "technologies", "programming_languages",
                  "frameworks", "cloud", "databases", "tools"):
            for s in (resume.get(f) or []):
                v = (s or "").strip().lower()
                if v:
                    candidate_skills.add(v)
    required: set = set()
    for j in real_jobs or []:
        for s in (j.get("skills") or []):
            v = (s or "").strip().lower()
            if v:
                required.add(v)
    overlap = sorted(required & candidate_skills)
    if overlap:
        sample = ", ".join(overlap[:3])
        out.append(
            f"Highlight the following skills higher on your resume "
            f"(already in your skill list, used by these companies): {sample}"
        )

    # 2. Add missing skills to a projects section via reframing
    for gap in (top_gaps or [])[:2]:
        out.append(
            f"Address the '{gap}' gap by reframing an existing project "
            f"to mention the adjacent concept (or build a small weekend project)"
        )

    # 3. Reorder existing projects
    candidate_projects = []
    if resume:
        for p in (resume.get("projects") or []):
            if isinstance(p, dict):
                candidate_projects.append(p.get("name") or "")
            else:
                candidate_projects.append(str(p))
    if candidate_projects:
        out.append(
            "Reorder projects so the most relevant to AI-startup hiring "
            f"comes first: currently {', '.join(candidate_projects[:3])}"
        )

    # 4. Add metrics to bullets
    out.append(
        "Add a quantifiable metric (%/ms/$/QPS/users) to at least 2 existing bullets"
    )

    # 5. Soft skills
    if overlap or top_gaps:
        out.append(
            "Use keywords from the JD (the high-overlap skills) in your Summary section"
        )

    return out[:5]


# ─── Interview preparation topics ───────────────────────────────────────

def _interview_prep(
    top_gaps: List[str],
    required_skills: List[str],
) -> List[str]:
    """Return 5-7 interview prep topics drawn from real skills."""
    out: List[str] = []
    # Tech stack topics
    for s in required_skills[:5]:
        out.append(s)
    # Add system design
    out.append("System Design (scalability, caching, data modeling)")
    # Add behavioural
    out.append("Behavioural questions (project deep-dives, conflict, leadership)")
    # If gaps exist, suggest a hands-on mini-project
    if top_gaps:
        out.append(
            f"Build a small hands-on project covering '{top_gaps[0]}' (top gap)"
        )
    return out[:7]


# ─── Networking tasks ──────────────────────────────────────────────────

def _networking_tasks(
    resume: Optional[Dict[str, Any]],
    real_jobs: List[Dict[str, Any]],
    high_priority: List[Dict[str, Any]],
) -> List[str]:
    out: List[str] = []
    # Generic-but-actionable: connect with one engineer per top company
    for h in high_priority[:3]:
        name = h.get("name") or "the top company"
        out.append(
            f"Connect with one engineer at {name} on LinkedIn "
            f"(mention a specific project on your resume)"
        )
    # Follow recruiters
    out.append(
        "Follow 2-3 technical recruiters on LinkedIn; engage with their posts weekly"
    )
    # Cold email founder (only if strategy suggests it)
    has_cold_email = any(
        (h.get("opportunity_v2") or {}).get("opportunity_recommendation_strategy")
        == "Cold Email Founder"
        for h in high_priority
    )
    if has_cold_email:
        out.append(
            "Cold-email the founder of one of your top opportunities "
            "(find email via Hunter.io or personal site)"
        )
    # Comment on company announcement
    out.append(
        "Comment thoughtfully on one company announcement per week"
    )
    return out[:4]


# ─── Follow-up plan ────────────────────────────────────────────────────

def _follow_up_plan(resume_present: bool) -> List[str]:
    """Deterministic follow-up schedule. No schedulers; just the plan."""
    out: List[str] = [
        "Day 3: Send a polite follow-up if no acknowledgement received",
        "Day 5: Follow up with one more person at the company on LinkedIn",
        "Day 10: If still no response, request feedback (or move on)",
        "Day 14: Final follow-up with a specific question; then close the loop",
    ]
    if not resume_present:
        out = [
            "Upload your resume first (Day 0); then the follow-up timeline below applies:",
        ] + out
    return out


# ─── Today tasks ───────────────────────────────────────────────────────

def _today_tasks(
    high_priority: List[Dict[str, Any]],
    gaps: List[str],
    has_resume: bool,
) -> List[str]:
    """Concrete actions for today. No fabrication."""
    out: List[str] = []
    if not has_resume:
        out.append("Upload your resume (PDF) on the Resume page")
        out.append("Re-check the Dashboard — the system now has your profile")
        out.append("Open the Companies page to see your top opportunities")
        return out
    # Has resume: actionable tasks
    for h in high_priority[:3]:
        name = h.get("name") or "top opportunity"
        out.append(f"Apply to {name} via the careers page (today)")
    if gaps:
        out.append(
            f"Address '{gaps[0]}' gap: add a short note to your resume "
            f"or build a 1-day project"
        )
    return out[:5]


# ─── This-week tasks (5 days) ───────────────────────────────────────

def _this_week_tasks(
    high_priority: List[Dict[str, Any]],
    medium_priority: List[Dict[str, Any]],
    gaps: List[str],
    networking: List[str],
) -> List[Dict[str, str]]:
    """Return ordered Mon-Fri tasks. Each item has {day, action}."""
    out: List[Dict[str, str]] = []
    if not high_priority and not medium_priority:
        out.append({"day": "Monday", "action": "Identify 5-10 target companies"})
        out.append({"day": "Tuesday", "action": "Tailor resume and cover letter"})
        out.append({"day": "Wednesday", "action": "Apply to your first company"})
        out.append({"day": "Thursday", "action": "Reach out via LinkedIn"})
        out.append({"day": "Friday", "action": "Track results, follow up"})
        return out

    # Monday: largest-priority apply
    if high_priority:
        first = high_priority[0].get("name") or "the top company"
        out.append({"day": "Monday", "action": f"Apply to {first} (priority 1)"})
    # Tuesday: tailor resume
    out.append({
        "day": "Tuesday",
        "action": "Tailor resume summary for the next 2 high-priority companies"
    })
    # Wednesday: second apply + networking
    if len(high_priority) > 1:
        second = high_priority[1].get("name") or "second-priority company"
        out.append({"day": "Wednesday", "action": f"Apply to {second} (priority 2)"})
    if networking:
        out.append({"day": "Wednesday", "action": networking[0]})
    # Thursday: medium + project
    if medium_priority:
        mid = medium_priority[0].get("name") or "mid-priority company"
        out.append({"day": "Thursday", "action": f"Apply to {mid} (priority 3)"})
    if gaps:
        out.append({
            "day": "Thursday",
            "action": f"Build a small project for '{gaps[0]}' gap (overnight)"
        })
    # Friday: follow-up
    out.append({
        "day": "Friday",
        "action": "Follow-up on Monday's application; networking for next week"
    })
    if len(networking) > 1:
        out.append({"day": "Friday", "action": networking[1]})
    return out[:5]


# ─── Weekly goal synthesis ───────────────────────────────────────────

def _weekly_goal(
    n_high: int, n_medium: int, n_long: int, has_resume: bool,
) -> str:
    if not has_resume:
        return "Upload your resume this week; the system will then produce an actionable plan."
    if n_high == 0 and n_medium == 0:
        return "No immediate opportunities — invest this week in skill-building and networking."
    if n_high >= 3:
        return f"Apply to your top {n_high} opportunities this week and reach out to 2-3 engineers."
    return f"Apply to {n_high + n_medium} opportunities and strengthen 1 weak skill."


# ─── Time estimate ───────────────────────────────────────────────────

def _estimate_hours(
    n_high: int, n_medium: int, has_resume: bool, n_gaps: int,
) -> int:
    if not has_resume:
        return 0
    base = 0
    base += min(5, n_high) * 1   # 1 hour per top application
    base += min(3, n_medium) * 1
    base += 1                    # 1h networking
    if n_gaps > 0:
        base += 2              # 2h gap project
    return base


# ─── Portfolio view ─────────────────────────────────────────────────

def _portfolio_view(
    high_priority: List[Dict[str, Any]],
    medium_priority: List[Dict[str, Any]],
    long_term: List[Dict[str, Any]],
    company_records: List[Dict[str, Any]],
    has_resume: bool,
) -> Dict[str, Any]:
    avg_opp = 0
    max_opp = 0
    avg_match = 0
    if company_records:
        scores = [
            (c.get("opportunity_v2") or {}).get("opportunity_score", 0)
            for c in company_records
        ]
        scores = [s for s in scores if s]
        if scores:
            avg_opp = sum(scores) // len(scores)
            max_opp = max(scores)
    return {
        "text": (
            f"You have "
            f"{len(high_priority)} companies to apply today/this week, "
            f"{len(medium_priority)} medium-priority opportunities, "
            f"{len(long_term)} long-term targets"
        ),
        "high_priority_count": len(high_priority),
        "medium_priority_count": len(medium_priority),
        "long_term_count": len(long_term),
        "total_companies": len(company_records),
        "average_opportunity_score": avg_opp,
        "highest_opportunity_score": max_opp,
        "average_resume_match": avg_match,
        "resume_uploaded": has_resume,
    }


# ─── Tier-based partition ───────────────────────────────────────────

def _partition_by_tier(
    company_records: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split ranked companies by opportunity tier.
    Returns (high, medium, long_term) lists.
    """
    high: List[Dict[str, Any]] = []
    medium: List[Dict[str, Any]] = []
    long_term: List[Dict[str, Any]] = []
    for c in company_records:
        ov2 = c.get("opportunity_v2") or {}
        tier = ov2.get("opportunity_tier") or "D"
        if tier in ("S", "A"):
            high.append(c)
        elif tier == "B":
            medium.append(c)
        else:  # C, D
            long_term.append(c)
    return high, medium, long_term


# ─── Gap extraction (reuse candidate_skill_set logic) ─────────────

def _extract_candidate_skill_set(resume: Optional[Dict[str, Any]]) -> set:
    if not resume:
        return set()
    out = set()
    for f in ("skills", "technologies", "programming_languages",
              "frameworks", "cloud", "databases", "tools"):
        for s in (resume.get(f) or []):
            v = (s or "").strip().lower()
            if v:
                out.add(v)
    return out


def _collect_required_skills(real_jobs: List[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    seen = set()
    for j in real_jobs or []:
        for s in (j.get("skills") or []):
            v = (s or "").strip()
            if v and v not in seen:
                seen.add(v)
                out.append(v)
    return out


def _top_gaps(candidate_skills: set, real_jobs: List[Dict[str, Any]], k: int = 3) -> List[str]:
    required: List[str] = []
    seen = set()
    for j in real_jobs or []:
        for s in (j.get("skills") or []):
            v = (s or "").strip()
            if v and v not in seen:
                seen.add(v)
                required.append(v)
    gaps = [s for s in required if s.lower() not in candidate_skills]
    return gaps[:k]


# ─── Public entry point ───────────────────────────────────────────

def build_career_action_plan(
    company_records: List[Dict[str, Any]],
    resume: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Consume the company list (each with the existing
    ``opportunity_v2`` + ``intelligence`` + ``enrichment`` + ``scores``)
    and produce a unified Career Action Plan.
    """
    has_resume = resume is not None

    # Aggregate real_jobs across all companies (for skill-gap analysis)
    real_jobs: List[Dict[str, Any]] = []
    for c in company_records:
        for j in (c.get("job_intelligence") or {}).get("jobs") or []:
            real_jobs.append(j)

    # Partition by tier
    high, medium, long_term = _partition_by_tier(company_records)
    # Apply application queue ordering
    for grp in (high, medium, long_term):
        grp.sort(key=lambda c: c.get("opportunity_v2", {}).get(
            "recommended_application_order", 9999))

    # Skill gap analysis
    candidate_skills = _extract_candidate_skill_set(resume)
    top_gaps = _top_gaps(candidate_skills, real_jobs, k=3)
    required_skills = _collect_required_skills(real_jobs)

    # Build each section
    today = _today_tasks(high, top_gaps, has_resume)
    this_week = _this_week_tasks(high, medium, top_gaps, [])
    resume_imps = _resume_improvements(resume, real_jobs, top_gaps)
    interview = _interview_prep(top_gaps, required_skills)
    networking = _networking_tasks(resume, real_jobs, high)
    follow_up = _follow_up_plan(has_resume)
    portfolio = _portfolio_view(high, medium, long_term, company_records, has_resume)
    weekly_goal = _weekly_goal(
        len(high), len(medium), len(long_term), has_resume
    )
    hours = _estimate_hours(
        len(high), len(medium), has_resume, len(top_gaps)
    )

    return {
        "weekly_goal": weekly_goal,
        "today_tasks": today,
        "this_week_tasks": this_week,
        "resume_improvements": resume_imps,
        "interview_preparation": interview,
        "networking_tasks": networking,
        "follow_up_plan": follow_up,
        "high_priority_companies": [c.get("name") for c in high],
        "medium_priority_companies": [c.get("name") for c in medium],
        "long_term_targets": [c.get("name") for c in long_term],
        "estimated_hours_required": hours,
        "portfolio": portfolio,
    }


# ─── Single-call dashboard helper ─────────────────────────────────

def build_career_action_plan_with_details(
    company_records: List[Dict[str, Any]],
    resume: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Convenience wrapper that returns the plan plus a few more
    human-readable strings suitable for the dashboard header.

    RC-4 — fix ``next_action`` so it never tells the user to upload
    a resume they already uploaded. When the planner produced no
    urgent ``today_tasks``, fall back to the highest-ranked
    opportunity in the portfolio instead.
    """
    plan = build_career_action_plan(company_records, resume)
    has_resume = resume is not None

    if not has_resume:
        plan["next_action"] = "Upload your resume to begin the plan."
    elif plan.get("today_tasks"):
        first = plan["today_tasks"][0]
        plan["next_action"] = first
    else:
        # Resume exists but planner produced no urgent tasks. Give
        # the user a context-aware action from the portfolio.
        high_priority = plan.get("high_priority_companies") or []
        medium_priority = plan.get("medium_priority_companies") or []
        long_term = plan.get("long_term_targets") or []
        if high_priority:
            plan["next_action"] = (
                f"Apply to {high_priority[0]} — your highest-ranked opportunity"
            )
        elif medium_priority:
            plan["next_action"] = (
                f"Review {medium_priority[0]} — your next medium-priority target"
            )
        elif long_term:
            plan["next_action"] = (
                f"Review your top companies — start with {long_term[0]}"
            )
        else:
            plan["next_action"] = (
                "Generate your weekly report to see a personalised action plan"
            )
    return plan
