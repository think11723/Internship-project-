"""Career Planner endpoint — Sprint 14.4.

Thin wrapper over ``career_action_planner.build_career_action_plan_with_details``.
The planner module was implemented in Sprint 13 but never wired into
any HTTP endpoint. This route aggregates the latest resume and the
cached company list and returns the planner's full output.

The planner produces a single payload:
  - weekly_goal                  (str)
  - today_tasks                  (List[str])
  - this_week_tasks              (List[str])
  - resume_improvements         (List[str])
  - interview_preparation       (List[str])
  - networking_tasks            (List[str])
  - follow_up_plan               (List[str])
  - high_priority_companies      (List[str])
  - medium_priority_companies    (List[str])
  - long_term_targets            (List[str])
  - estimated_hours_required     (int)
  - portfolio                    (dict — text + counts)
  - next_action                  (str)

The endpoint never invents new intelligence — it returns exactly
what the planner already produces.

Graceful behaviour when no resume is uploaded:
  - HTTP 200 with ``{"requires_resume": true, ...}`` envelope so the
    frontend can render the same "upload your resume" UX used
    elsewhere.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Any, Dict, List, Optional

from app.core.auth import get_current_user_id
from app.db.session import get_db
from app.models.resume import Resume
from app.services import orchestrator
from app.services.career_action_planner import (
    build_career_action_plan_with_details,
)
from app.services.user_scope import get_user_resume

router = APIRouter()


def _shape_company_for_planner(company: Dict[str, Any]) -> Dict[str, Any]:
    """Project a cached company record into the planner's expected shape.

    The planner reads three fields per company:
      - ``name``
      - ``opportunity_v2.recommended_application_order``
      - ``job_intelligence.jobs``

    We also forward the enrichment block so future planner
    iterations can read hiring signals without a second fetch.
    """
    rec = company.get("recommendation") or {}
    return {
        "name": company.get("name"),
        "opportunity_v2": rec.get("opportunity_v2") or {},
        "job_intelligence": company.get("job_intelligence") or {},
        "enrichment": company.get("enrichment") or {},
        "intelligence": rec.get("intelligence") or {},
    }


def _resume_dict_for_planner(resume: Resume) -> Dict[str, Any]:
    """Project a Resume ORM row into the dict shape the planner reads.

    The planner reads (today/this_week/resume_improvements helpers):
      - ``resume.get("skills")`` + ``"technologies"``,
        ``"programming_languages"``, ``"frameworks"``,
        ``"cloud"``, ``"databases"``, ``"tools"`` for the
        candidate skill set.

    The Resume ORM model exposes ``skills`` / ``technologies`` as
    first-class columns. The other category lists live inside
    ``analysis_json`` (produced by the resume upload pipeline).
    We pull everything from there so the planner sees a unified
    dict regardless of which JSON sub-key the data lives under.
    """
    analysis = resume.analysis_json or {}
    return {
        "id": resume.id,
        "name": resume.name,
        "email": resume.email,
        "summary": resume.summary,
        "skills": list(resume.skills or []),
        "technologies": list(resume.technologies or []),
        "frameworks": list(analysis.get("frameworks") or []),
        "programming_languages": list(
            analysis.get("programming_languages") or []
        ),
        "cloud": list(analysis.get("cloud") or []),
        "databases": list(analysis.get("databases") or []),
        "tools": list(analysis.get("tools") or []),
        "experience": list(resume.experience or []),
        "education": list(resume.education or []),
        "projects": list(resume.projects or []),
        "strengths": list(resume.strengths or []),
        "analysis_json": analysis,
        "years_of_experience": (
            analysis.get("years_of_experience") or ""
        ),
    }


@router.get("/career-plan", summary="Aggregated Career Action Plan")
async def get_career_plan(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Aggregate the authenticated user's resume and the cached company
    list and return the Career Action Planner's full output.

    The company list is GLOBAL; the plan built from it is entirely
    derived from the caller's own resume.

    No resume? Same ``requires_resume`` envelope used by every other
    resume-aware endpoint on this API.
    """
    # 1. This user's resume (single-active policy, scoped by user_id).
    latest_resume: Optional[Resume] = get_user_resume(db, user_id)

    # 2. Graceful empty state.
    if latest_resume is None:
        return {
            "requires_resume": True,
            "message": "Upload your resume to unlock the career action plan.",
            "weekly_goal": "",
            "today_tasks": [],
            "this_week_tasks": [],
            "resume_improvements": [],
            "interview_preparation": [],
            "networking_tasks": [],
            "follow_up_plan": [],
            "high_priority_companies": [],
            "medium_priority_companies": [],
            "long_term_targets": [],
            "estimated_hours_required": 0,
            "portfolio": {
                "text": "Upload your resume to begin the plan.",
                "high_priority_count": 0,
                "medium_priority_count": 0,
                "long_term_count": 0,
                "total_companies": 0,
                "average_opportunity_score": 0,
                "highest_opportunity_score": 0,
                "average_resume_match": 0,
                "resume_uploaded": False,
            },
            "next_action": "Upload your resume to begin the plan.",
        }

    # 3. Companies list — reuse the same smart-loader the rest of the
    # app uses (cache → live → seed). Zero new logic.
    companies: List[Dict[str, Any]] = orchestrator._load_companies()
    planner_records: List[Dict[str, Any]] = [
        _shape_company_for_planner(c) for c in companies
    ]

    # 4. Build the plan (Sprint 13 module — untouched).
    resume_dict = _resume_dict_for_planner(latest_resume)
    plan = build_career_action_plan_with_details(planner_records, resume_dict)

    # 5. Decorate with the same envelope flag every resume-aware
    # endpoint exposes, so the frontend can use one render branch.
    plan["requires_resume"] = False
    plan["resume_uploaded"] = True
    return plan
