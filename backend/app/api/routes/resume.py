"""Resume endpoints."""

import os
import uuid
import time
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.logging import logger, log_performance
from app.core.middleware import sanitize_filename, validate_mime_type
from app.db.session import get_db
from app.models.resume import Resume
from app.schemas.resume import (
    EducationItem,
    ExperienceItem,
    ResumeMetadataResponse,
    ResumeProfile,
    ResumeUploadResponse,
)
from app.services.resume_service import ResumeIntelligenceService

router = APIRouter()

MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_MIME_TYPES = {"application/pdf"}
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


# In-memory job registry for upload progress.
# Keyed by job_id (UUID string). Each entry is a dict with the
# current stage, last update timestamp, terminal status, and
# the final result payload (when status == "done").
# Entries are pruned after JOB_TTL_SECONDS to keep the dict bounded.
JOB_TTL_SECONDS = 300
_JOB_STATE: Dict[str, Dict[str, Any]] = {}


def _job_update(job_id: Optional[str], stage: str, status: str = "running",
                error: Optional[str] = None, result: Optional[Dict[str, Any]] = None) -> None:
    """Update (or create) a job state entry. Safe to call with job_id=None."""
    if not job_id:
        return
    _JOB_STATE[job_id] = {
        "stage": stage,
        "status": status,
        "updated_at": time.time(),
        "error": error,
        "result": result,
    }


def _job_prune() -> None:
    """Remove job entries older than JOB_TTL_SECONDS that have finished."""
    cutoff = time.time() - JOB_TTL_SECONDS
    stale = [jid for jid, entry in _JOB_STATE.items()
             if entry.get("status") in {"done", "failed"} and entry.get("updated_at", 0) < cutoff]
    for jid in stale:
        _JOB_STATE.pop(jid, None)


def _serialize_analysis(resume: Resume) -> Dict[str, Any]:
    """Reconstruct a ResumeUploadResponse-shaped payload from a Resume row."""
    rich = resume.analysis_json if isinstance(resume.analysis_json, dict) else {}
    raw_text = resume.raw_text or ""
    profile = ResumeProfile(
        name=rich.get("name") or resume.name or "",
        email=rich.get("email") or resume.email or "",
        phone=rich.get("phone") or resume.phone or "",
        location=rich.get("location") or resume.location or "",
        professional_summary=rich.get("professional_summary") or resume.summary or "",
        years_of_experience=rich.get("years_of_experience") or "",
        skills=rich.get("skills") or list(resume.skills or []),
        technologies=rich.get("technologies") or list(resume.technologies or []),
        frameworks=rich.get("frameworks") or [],
        programming_languages=rich.get("programming_languages") or [],
        cloud=rich.get("cloud") or [],
        databases=rich.get("databases") or [],
        tools=rich.get("tools") or [],
        projects=rich.get("projects") or list(resume.projects or []),
        experience=[
            ExperienceItem(**item) if isinstance(item, dict) else ExperienceItem()
            for item in (rich.get("experience") or resume.experience or [])
        ],
        education=[
            EducationItem(**item) if isinstance(item, dict) else EducationItem()
            for item in (rich.get("education") or resume.education or [])
        ],
        strengths=rich.get("strengths") or list(resume.strengths or []),
        recommended_roles=rich.get("recommended_roles") or [],
    )
    summary = profile.professional_summary or (raw_text[:300] + ("..." if len(raw_text) > 300 else ""))
    return {
        "success": True,
        "profile": profile.model_dump(),
        "extracted_text": raw_text,
        "summary": summary,
    }


@router.post("/upload", response_model=ResumeUploadResponse)
async def upload_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    x_upload_id: Optional[str] = Header(None, alias="X-Upload-Id"),
):
    """Upload a PDF resume, extract its text, analyze it, and save the structured profile.

    Validates file type, size, and content before processing. Uses AI for structured
    extraction with local fallback if AI is unavailable.

    If the client sends an ``X-Upload-Id`` header, the route writes per-stage
    progress to the in-memory job registry so the frontend can poll
    ``GET /api/resume/upload-status/{job_id}`` for real stage updates.
    """
    start_time = time.time()
    temp_file_path = None
    job_id = x_upload_id

    try:
        filename = file.filename or "resume.pdf"
        content_type = file.content_type or ""

        # Sanitize filename
        safe_filename = sanitize_filename(filename)

        # Validate MIME type
        if not validate_mime_type(content_type, safe_filename):
            raise HTTPException(
                status_code=400,
                detail="Invalid file type. Only PDF files are allowed."
            )

        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty file")

        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail="File too large. Maximum size is 10MB"
            )

        file_id = str(uuid.uuid4())
        temp_file_path = UPLOAD_DIR / f"{file_id}.pdf"
        temp_file_path.write_bytes(content)

        _job_update(job_id, "Reading PDF", "running")

        # Process resume with timing + per-stage progress writes
        service = ResumeIntelligenceService()
        try:
            process_start = time.time()

            def _progress(stage: str) -> None:
                _job_update(job_id, stage, "running")

            profile, extracted_text = service.process_resume(
                str(temp_file_path),
                progress_callback=_progress,
            )
            process_duration = (time.time() - process_start) * 1000
            log_performance("resume_processing", process_duration, {"file_id": file_id})
        except ValueError as exc:
            _job_update(job_id, "Failed", "failed", error=str(exc))
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.error("Resume intelligence failed: %s", exc)
            _job_update(job_id, "Failed", "failed", error=str(exc))
            raise HTTPException(
                status_code=500,
                detail="Failed to analyze resume with AI. Please try again."
            ) from exc

        _job_update(job_id, "Finalizing Analysis", "running")

        resume = Resume(
            original_filename=safe_filename,
            name=profile.name,
            email=profile.email,
            phone=profile.phone,
            location=profile.location,
            summary=profile.professional_summary,
            skills=profile.skills,
            experience=[item.model_dump() for item in profile.experience],
            education=[item.model_dump() for item in profile.education],
            projects=profile.projects,
            technologies=profile.technologies,
            strengths=profile.strengths,
            analysis_json=profile.model_dump(),
            raw_text=extracted_text,
            file_size=len(content),
        )

        db.add(resume)
        db.commit()
        db.refresh(resume)

        logger.info("Resume stored in database with ID: %s", resume.id)

        if temp_file_path and temp_file_path.exists():
            os.remove(temp_file_path)

        summary = profile.professional_summary or (extracted_text[:300] + ("..." if len(extracted_text) > 300 else ""))

        total_duration = (time.time() - start_time) * 1000
        log_performance("resume_upload_total", total_duration, {"resume_id": resume.id})

        response_payload = {
            "success": True,
            "profile": profile.model_dump(),
            "extracted_text": extracted_text,
            "summary": summary,
        }
        _job_update(job_id, "Completed", "done", result=response_payload)
        return ResumeUploadResponse(
            success=True,
            profile=profile,
            extracted_text=extracted_text,
            summary=summary,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Unexpected error during resume upload: %s", exc)
        _job_update(job_id, "Failed", "failed", error=str(exc))
        if temp_file_path and temp_file_path.exists():
            try:
                os.remove(temp_file_path)
            except Exception:
                pass
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred. Please try again."
        ) from exc


# ---------- Resume Management endpoints ----------

@router.get("/latest", response_model=ResumeMetadataResponse)
async def get_latest_resume(db: Session = Depends(get_db)):
    """Return lightweight metadata for the most-recently parsed resume.

    Used by the "Current Resume" card on the upload page. Returns 404 when
    no resume has been uploaded yet.
    """
    resume = db.query(Resume).order_by(Resume.parsed_at.desc()).first()
    if resume is None:
        raise HTTPException(status_code=404, detail="No resume uploaded yet")

    rich = resume.analysis_json if isinstance(resume.analysis_json, dict) else {}
    skills_count = len(rich.get("skills") or list(resume.skills or []))
    status = "analyzed" if rich else "processing"

    return ResumeMetadataResponse(
        id=resume.id,
        original_filename=resume.original_filename or "",
        parsed_at=resume.parsed_at.isoformat() if resume.parsed_at else None,
        name=resume.name or rich.get("name") or "",
        email=resume.email or rich.get("email") or "",
        summary=resume.summary or rich.get("professional_summary") or "",
        skills_count=skills_count,
        file_size=resume.file_size,
        status=status,
    )


@router.get("/latest/analysis")
async def get_latest_resume_analysis(db: Session = Depends(get_db)):
    """Return the full ``ResumeUploadResponse``-shaped payload for the latest resume.

    Used by the "View Resume" action on the upload page. Returns 404 when
    no resume exists.
    """
    resume = db.query(Resume).order_by(Resume.parsed_at.desc()).first()
    if resume is None:
        raise HTTPException(status_code=404, detail="No resume uploaded yet")
    return _serialize_analysis(resume)


@router.delete("/latest")
async def delete_latest_resume(db: Session = Depends(get_db)):
    """Delete ALL parsed resumes and invalidate related caches.

    The application enforces a single-active-resume policy, so the
    user-facing "Delete Resume" action must fully clear state and
    return the dashboard to first-use. Returns 404 when no resume
    exists. Always invalidates the in-memory job-state registry and
    the discovery cache.
    """
    count = db.query(Resume).count()
    if count == 0:
        raise HTTPException(status_code=404, detail="No resume to delete")

    _job_prune()
    _JOB_STATE.clear()

    db.query(Resume).delete()
    db.commit()

    # Invalidate the company discovery cache so the next orchestration
    # run reflects the absence of the resume.
    try:
        from app.services.orchestrator import invalidate_cache
        invalidate_cache()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to invalidate discovery cache: %s", exc)

    return {"success": True, "deleted_count": count}


@router.get("/upload-status/{job_id}")
async def get_upload_status(job_id: str):
    """Return the current stage of an in-flight upload job.

    The job is created when the client posts a file to
    ``/api/resume/upload`` with the same id in the ``X-Upload-Id`` header.
    Returns 404 when the job is unknown (expired or never existed).
    """
    _job_prune()
    entry = _JOB_STATE.get(job_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Unknown or expired job")
    return {
        "job_id": job_id,
        "stage": entry.get("stage"),
        "status": entry.get("status"),
        "updated_at": entry.get("updated_at"),
        "error": entry.get("error"),
        "result": entry.get("result"),
    }
