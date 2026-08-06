"""Workflow endpoints - high-level orchestration entry points.

These endpoints trigger multi-step AI workflows that coordinate
internal services. The frontend talks to these endpoints, not to
individual services directly.
"""

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Any, Dict, Optional

from app.core.auth import get_current_user_id
from app.db.session import get_db
from app.services.orchestrator import run_weekly_report

router = APIRouter()


class WeeklyReportResponse(BaseModel):
    """Response model for weekly career intelligence report."""
    summary: Optional[str] = Field(None, description="Report summary")
    candidate: Optional[Dict[str, Any]] = Field(None, description="Candidate profile")
    generated_at: Optional[str] = Field(None, description="Generation timestamp")
    companies_found: Optional[int] = Field(None, description="Number of companies analyzed")
    top_matches: Optional[list] = Field(None, description="Top 3 company matches")
    cover_letter: Optional[Dict[str, str]] = Field(None, description="Generated cover letter")
    market_summary: Optional[Dict[str, Any]] = Field(None, description="Market intelligence summary")
    industry_breakdown: Optional[list] = Field(None, description="Industry breakdown")
    career_intelligence: Optional[Dict[str, Any]] = Field(None, description="Career intelligence")
    technology_breakdown: Optional[list] = Field(None, description="Technology breakdown")
    top_strengths: Optional[list] = Field(None, description="Top candidate strengths")
    top_skill_gaps: Optional[list] = Field(None, description="Top skill gaps")


class RequiresResumeResponse(BaseModel):
    """Response when no resume is uploaded."""
    requires_resume: bool = Field(True, description="Indicates resume is required")
    message: str = Field(..., description="Message to user")


@router.post(
    "/weekly-report",
    status_code=status.HTTP_200_OK,
    summary="Generate Weekly Career Report",
    description="Trigger the weekly career intelligence report workflow",
    responses={
        200: {
            "description": "Report generated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "summary": "Your weekly career intelligence report",
                        "candidate": {"name": "John Doe", "skills": ["Python", "TypeScript"]},
                        "generated_at": "2025-01-21T12:00:00Z",
                        "companies_found": 20,
                        "top_matches": [],
                        "cover_letter": None,
                        "market_summary": {},
                        "industry_breakdown": [],
                        "career_intelligence": {},
                        "technology_breakdown": [],
                        "top_strengths": [],
                        "top_skill_gaps": []
                    }
                }
            }
        }
    }
)
async def weekly_report(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Trigger the weekly career intelligence report workflow.

    Internally this will coordinate Resume -> Discovery -> Research ->
    Matching -> Generation -> Report services. For now it returns a
    Demo Data-backed report personalized by the authenticated user's
    uploaded resume, or a requires_resume payload if that user has no
    resume. Company discovery is global; everything derived from the
    resume is scoped to the caller.

    Returns:
        Weekly career intelligence report payload, or a
        requires_resume payload if no resume has been uploaded.
    """
    return run_weekly_report(db, user_id)