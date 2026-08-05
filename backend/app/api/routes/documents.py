"""
Document generation endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Dict, Optional

from app.db.session import get_db
from app.models.resume import Resume
from app.services.generation_service import generate_cover_letter
from app.services.orchestrator import _build_candidate, _load_companies

router = APIRouter()


class GenerateDocumentRequest(BaseModel):
    """Request body for on-demand cover letter generation."""
    company_name: str = Field(..., description="Name of the target company")


class CoverLetterResponse(BaseModel):
    """Response from cover letter generation."""
    company: str = Field(..., description="Target company name")
    content: str = Field(..., description="Generated cover letter content")


@router.post(
    "/generate",
    status_code=status.HTTP_200_OK,
    summary="Generate Cover Letter",
    description="Generate a personalized cover letter for a specific company",
    responses={
        200: {
            "description": "Cover letter generated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "company": "Anthropic",
                        "content": "Dear Hiring Team,\n\nI am writing to express my interest..."
                    }
                }
            }
        },
        404: {
            "description": "Company not found"
        },
        400: {
            "description": "No resume uploaded"
        },
        503: {
            "description": "Cover letter generation temporarily unavailable"
        }
    }
)
async def generate_document(
    payload: GenerateDocumentRequest,
    db: Session = Depends(get_db),
):
    """Generate a personalized cover letter for a specific company.

    Reuses the existing ``generate_cover_letter`` service. Fails
    gracefully if no resume has been uploaded, the company is not in
    the Demo Data set, or the LLM call errors.
    """
    company = _find_company(payload.company_name)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company '{payload.company_name}' not found",
        )

    latest_resume = (
        db.query(Resume).order_by(Resume.parsed_at.desc()).first()
    )
    if latest_resume is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload your resume before generating a cover letter.",
        )

    candidate = _build_candidate(latest_resume)
    cover_letter = generate_cover_letter(candidate, company)

    if cover_letter is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cover letter generation is temporarily unavailable. Please try again.",
        )

    return cover_letter


def _find_company(company_name: str) -> Optional[Dict]:
    """Find a company by name (case-insensitive) in the active company set."""
    companies = _load_companies()
    target = company_name.strip().lower()
    for entry in companies:
        if entry.get("name", "").lower() == target:
            return entry
    return None