"""Resume schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ExperienceItem(BaseModel):
    """Experience item schema."""

    company: str = ""
    role: str = ""
    duration: str = ""
    description: str = ""


class EducationItem(BaseModel):
    """Education item schema."""

    institution: str = ""
    degree: str = ""
    year: str = ""


class ResumeProfile(BaseModel):
    """Structured resume profile extracted from a resume PDF."""

    name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    professional_summary: str = ""
    years_of_experience: str = ""
    skills: List[str] = []
    technologies: List[str] = []
    frameworks: List[str] = []
    programming_languages: List[str] = []
    cloud: List[str] = []
    databases: List[str] = []
    tools: List[str] = []
    projects: List[str] = []
    experience: List[ExperienceItem] = []
    education: List[EducationItem] = []
    strengths: List[str] = []
    recommended_roles: List[str] = []


class ResumeMetadataResponse(BaseModel):
    """Lightweight metadata for the most-recently parsed resume.

    Returned by ``GET /api/resume/latest`` for the "Current Resume" card.
    Excludes the full ``raw_text`` and structured profile to keep the
    payload small.
    """

    id: int
    original_filename: str
    parsed_at: Optional[str] = None
    name: str = ""
    email: str = ""
    summary: str = ""
    skills_count: int = 0
    file_size: Optional[int] = None
    status: str = "analyzed"


class Resume(BaseModel):
    """Schema for resume response."""

    id: int
    original_filename: str
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    summary: Optional[str] = None
    skills: Optional[List[str]] = None
    experience: Optional[List[dict]] = None
    education: Optional[List[dict]] = None
    projects: Optional[List[str]] = None
    technologies: Optional[List[str]] = None
    strengths: Optional[List[str]] = None
    analysis_json: Optional[dict] = None
    parsed_at: datetime

    class Config:
        from_attributes = True


class ResumeUploadResponse(BaseModel):
    """Response returned after a resume upload and analysis."""

    success: bool
    profile: ResumeProfile
    extracted_text: Optional[str] = None
    summary: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standardized error response."""

    status: str = "error"
    message: str
    error_code: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    request_id: Optional[str] = None


class ValidationErrorResponse(BaseModel):
    """Validation error response."""

    status: str = "validation_error"
    message: str
    errors: List[Dict[str, Any]] = []
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    request_id: Optional[str] = None
