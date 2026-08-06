"""Per-user scoping helpers.

The single definition of "this user's resume" and "this user's upload
directory". Every route that touches resume-derived data goes through
here rather than writing its own query, so the scoping rule exists in
exactly one place.

Before this module existed, nine call sites independently ran
``db.query(Resume).order_by(Resume.parsed_at.desc()).first()`` — "the
most recently uploaded resume, by anyone". That expression was the
single-user assumption, and it is what this module replaces.
"""

import os
from pathlib import Path
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.resume import Resume

# Uploads root: configurable via ``FUNDFLOW_DATA_DIR`` so deployments
# can mount a persistent volume (e.g. ``/data``). Unchanged from the
# pre-migration location; only the per-user subdirectory is new.
UPLOAD_ROOT = Path(os.environ.get("FUNDFLOW_DATA_DIR", ".")) / "uploads"


def get_user_resume(db: Session, user_id: str) -> Optional[Resume]:
    """Return the active resume for ``user_id``, or None.

    The application enforces one active resume per user (uploading
    replaces), so ``parsed_at desc`` is belt-and-braces: it guarantees a
    deterministic pick if a replace ever half-completes.
    """
    return (
        db.query(Resume)
        .filter(Resume.user_id == user_id)
        .order_by(Resume.parsed_at.desc())
        .first()
    )


def count_user_resumes(db: Session, user_id: str) -> int:
    """Count resumes belonging to ``user_id``."""
    return db.query(Resume).filter(Resume.user_id == user_id).count()


def delete_user_resumes(db: Session, user_id: str) -> int:
    """Delete every resume belonging to ``user_id``. Returns the count.

    Scoped by construction — it is not possible to call this in a way
    that touches another user's rows.
    """
    deleted = (
        db.query(Resume)
        .filter(Resume.user_id == user_id)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted


def user_upload_dir(user_id: str) -> Path:
    """Return (creating if needed) the upload directory for ``user_id``.

    ``user_id`` is safe as a path segment: ``app.core.auth`` validates it
    against ``^[A-Za-z0-9_-]{1,128}$`` before any request reaches a
    route, which excludes ``.``, ``/``, ``\\`` and null bytes. The
    assertion below is a cheap backstop so a future caller that bypasses
    the dependency fails loudly instead of writing outside the root.
    """
    assert user_id and "/" not in user_id and "\\" not in user_id and ".." not in user_id, (
        f"unsafe user_id for filesystem use: {user_id!r}"
    )
    target = UPLOAD_ROOT / user_id
    target.mkdir(parents=True, exist_ok=True)
    return target


def purge_user_upload_dir(user_id: str) -> List[str]:
    """Remove any leftover files in the user's upload directory.

    Uploaded PDFs are deleted immediately after parsing, so this is
    normally a no-op. It exists because that cleanup has been observed
    to fail (an orphaned PDF was found in ``uploads/``), and resume
    deletion is the natural place to reclaim the space. Returns the
    names of the files removed.
    """
    target = UPLOAD_ROOT / user_id
    if not target.is_dir():
        return []
    removed: List[str] = []
    for entry in target.iterdir():
        if entry.is_file():
            try:
                entry.unlink()
                removed.append(entry.name)
            except OSError:
                # Best-effort reclamation; a locked file must not break
                # the user-facing delete.
                pass
    return removed
