"""Resume endpoints."""

import os
import uuid
import time
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
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
from app.services.user_scope import (
    UPLOAD_ROOT,
    count_user_resumes,
    delete_user_resumes,
    get_user_resume,
    purge_user_upload_dir,
    user_upload_dir,
)

router = APIRouter()

MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_MIME_TYPES = {"application/pdf"}

# Uploads root. Per-user subdirectories are created on demand by
# ``user_upload_dir``; see app/services/user_scope.py.
UPLOAD_DIR = UPLOAD_ROOT
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# In-memory job registry for upload progress.
#
# Keyed by ``(user_id, job_id)`` — NOT by job_id alone. The job_id is
# client-supplied, and each entry holds the full resume analysis in its
# ``result`` payload, so a bare job_id key let any caller who learned or
# guessed an id read someone else's parsed resume. The user_id in the
# key means a lookup can only ever return the caller's own job.
#
# Entries are pruned after JOB_TTL_SECONDS to keep the dict bounded.
JOB_TTL_SECONDS = 300
_JOB_STATE: Dict[Tuple[str, str], Dict[str, Any]] = {}


def _job_update(user_id: str, job_id: Optional[str], stage: str, status: str = "running",
                error: Optional[str] = None, result: Optional[Dict[str, Any]] = None) -> None:
    """Update (or create) a job state entry. Safe to call with job_id=None."""
    if not job_id:
        return
    _JOB_STATE[(user_id, job_id)] = {
        "stage": stage,
        "status": status,
        "updated_at": time.time(),
        "error": error,
        "result": result,
    }


def _job_prune() -> None:
    """Remove job entries older than JOB_TTL_SECONDS that have finished."""
    cutoff = time.time() - JOB_TTL_SECONDS
    stale = [key for key, entry in _JOB_STATE.items()
             if entry.get("status") in {"done", "failed"} and entry.get("updated_at", 0) < cutoff]
    for key in stale:
        _JOB_STATE.pop(key, None)


def _job_clear_user(user_id: str) -> None:
    """Drop every job entry belonging to ``user_id``.

    Replaces the previous ``_JOB_STATE.clear()``, which wiped every
    user's in-flight uploads whenever anyone deleted a resume.
    """
    for key in [k for k in _JOB_STATE if k[0] == user_id]:
        _JOB_STATE.pop(key, None)


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
    user_id: str = Depends(get_current_user_id),
    x_upload_id: Optional[str] = Header(None, alias="X-Upload-Id"),
):
    """Upload a PDF resume, extract its text, analyze it, and save the structured profile.

    Validates file type, size, and content before processing. Uses AI for structured
    extraction with local fallback if AI is unavailable.

    The resume is stored against the authenticated user. Uploading
    replaces only that user's previous resume; other users are never
    touched.

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
        # Per-user upload directory — one user's PDF can never land on
        # or overwrite another's. The file is still deleted once parsing
        # completes; the directory is the isolation boundary, not a
        # retention mechanism.
        temp_file_path = user_upload_dir(user_id) / f"{file_id}.pdf"
        temp_file_path.write_bytes(content)

        # Single-active-resume policy (Sprint 4 B1): uploading a new
        # resume REPLACES any existing row. The "Replace" button on
        # the frontend used to APPEND, leaking rows and confusing the
        # "latest" lookup.
        #
        # Scoped to this user. This delete previously had no WHERE
        # clause, so any upload destroyed every other user's resume.
        try:
            delete_user_resumes(db, user_id)
        except Exception as exc:
            logger.warning("Resume replace: pre-insert delete failed: %s", exc)
            db.rollback()

        _job_update(user_id, job_id, "Reading PDF", "running")

        # Process resume with timing + per-stage progress writes
        service = ResumeIntelligenceService()
        try:
            process_start = time.time()

            def _progress(stage: str) -> None:
                _job_update(user_id, job_id, stage, "running")

            profile, extracted_text = service.process_resume(
                str(temp_file_path),
                progress_callback=_progress,
            )
            process_duration = (time.time() - process_start) * 1000
            log_performance("resume_processing", process_duration, {"file_id": file_id})
        except ValueError as exc:
            _job_update(user_id, job_id, "Failed", "failed", error=str(exc))
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.error("Resume intelligence failed: %s", exc)
            _job_update(user_id, job_id, "Failed", "failed", error=str(exc))
            raise HTTPException(
                status_code=500,
                detail="Failed to analyze resume with AI. Please try again."
            ) from exc

        _job_update(user_id, job_id, "Finalizing Analysis", "running")

        resume = Resume(
            user_id=user_id,
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

        logger.info(
            "Resume stored in database with ID: %s (user_id=%s)",
            resume.id, user_id,
        )

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
        _job_update(user_id, job_id, "Completed", "done", result=response_payload)
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
        _job_update(user_id, job_id, "Failed", "failed", error=str(exc))
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
async def get_latest_resume(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Return lightweight metadata for the authenticated user's resume.

    Used by the "Current Resume" card on the upload page. Returns 404 when
    *this user* has not uploaded a resume — another user's upload does not
    satisfy the lookup.
    """
    resume = get_user_resume(db, user_id)
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
async def get_latest_resume_analysis(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Return the full ``ResumeUploadResponse``-shaped payload for this user's resume.

    Used by the "View Resume" action on the upload page. Returns 404 when
    this user has no resume.
    """
    resume = get_user_resume(db, user_id)
    if resume is None:
        raise HTTPException(status_code=404, detail="No resume uploaded yet")
    return _serialize_analysis(resume)


@router.delete("/latest")
async def delete_latest_resume(
    db: Session = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    """Delete the authenticated user's resume and all of their derived state.

    The application enforces a single-active-resume policy per user, so
    the user-facing "Delete Resume" action must fully clear that user's
    state and return their dashboard to first-use. Returns 404 when this
    user has no resume.

    Everything cleared here is user-scoped. The company discovery cache
    is GLOBAL and deliberately left alone — it is shared by every user
    and contains no resume-derived data, so dropping it on one user's
    delete would have discarded another user's working set and forced a
    full re-discovery. (The previous implementation did exactly that.)
    """
    count = count_user_resumes(db, user_id)
    if count == 0:
        raise HTTPException(status_code=404, detail="No resume to delete")

    _job_prune()
    _job_clear_user(user_id)

    delete_user_resumes(db, user_id)

    # Reclaim any PDF whose post-parse cleanup failed. No-op normally.
    purge_user_upload_dir(user_id)

    return {"success": True, "deleted_count": count}


@router.get("/upload-status/{job_id}")
async def get_upload_status(
    job_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Return the current stage of an in-flight upload job.

    The job is created when the client posts a file to
    ``/api/resume/upload`` with the same id in the ``X-Upload-Id`` header.
    Returns 404 when the job is unknown (expired, never existed, or
    belongs to a different user — the three are indistinguishable to the
    caller by design, so this cannot be used to probe for other users'
    job ids).
    """
    _job_prune()
    entry = _JOB_STATE.get((user_id, job_id))
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
