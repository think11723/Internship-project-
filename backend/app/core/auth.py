"""User identity resolution for per-user data scoping.

READ THIS BEFORE RELYING ON THIS MODULE
=======================================

This is an **interim implementation**. It provides *data isolation*,
NOT *authentication*.

The identity currently arrives as a plain ``X-User-Id`` request header
minted client-side. Nothing verifies it. Any caller can set the header
to any value and read/write that user's data. That is an accepted,
deliberate trade-off for the current stage of the migration: it makes
the backend structurally multi-tenant so that every personalized code
path is written against a real user identifier from day one.

Before this service is exposed publicly, ``_verify_bearer_token`` MUST
be implemented (see the TODO(firebase) markers below). When it is, the
``Authorization: Bearer <id-token>`` branch takes over and the
``X-User-Id`` fallback should be removed — no route, service, or helper
outside this file needs to change, because every caller depends only on
``get_current_user_id``.

Resolution order
----------------
1. ``Authorization: Bearer <token>`` → verified token subject.
   Currently a no-op hook that returns ``None`` and falls through.
2. ``X-User-Id`` header → the interim path.
3. Neither → behaviour depends on ``settings.REQUIRE_USER_SCOPE``:
   * ``True``  → HTTP 401.
   * ``False`` → the shared ``ANONYMOUS_USER_ID`` bucket (development
     default, so curl/Postman do not lock themselves out).

Note on the anonymous bucket: it is a *shared* bucket. Two callers that
both omit the header see each other's data. That is unchanged from the
pre-migration behaviour and is why ``REQUIRE_USER_SCOPE`` must be
flipped to ``True`` for any deployment.
"""

import re
from typing import Optional

from fastapi import Header, HTTPException, status

from app.core.config import settings
from app.core.logging import logger

# The bucket used when no identity is supplied and REQUIRE_USER_SCOPE is
# False. Deliberately a reserved value that the ID validator would also
# accept, so it round-trips through the same code paths as a real id.
ANONYMOUS_USER_ID = "anonymous"

# Sentinel assigned to pre-migration resume rows that predate user_id.
LEGACY_USER_ID = "legacy"

MAX_USER_ID_LENGTH = 128

# Strict allowlist. A user id is used verbatim as a filesystem path
# segment (``uploads/{user_id}/``), so anything that could traverse a
# directory — ``.``, ``/``, ``\``, ``:``, null bytes — is rejected
# outright rather than sanitized. Note that ValidationMiddleware only
# inspects query parameters, not headers, so this is the sole guard on
# this input.
#
# This charset accepts both shapes we care about:
#   * Firebase UIDs   — 28 chars, alphanumeric
#   * browser UUID v4 — hex with dashes
_USER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,%d}$" % MAX_USER_ID_LENGTH)


def _verify_bearer_token(token: str) -> Optional[str]:
    """Verify a bearer token and return its subject (the user id).

    TODO(firebase): implement with the Firebase Admin SDK:

        import firebase_admin
        from firebase_admin import auth as firebase_auth
        decoded = firebase_auth.verify_id_token(token)
        return decoded["uid"]

    Requires ``firebase-admin`` in requirements.txt and credentials via
    ``FIREBASE_CREDENTIALS_JSON`` / ``GOOGLE_APPLICATION_CREDENTIALS``.
    Revoked-token checks should use ``check_revoked=True``.

    Until that lands this returns ``None`` so the caller falls through
    to the interim header. It deliberately does NOT trust the token's
    unverified payload — an unverified JWT is attacker-controlled data,
    so reading a ``sub`` claim out of it would be strictly worse than
    ignoring it.
    """
    return None


def _validate_user_id(raw: str, source: str) -> str:
    """Validate and return a user id, or raise HTTP 400.

    ``source`` names the header the value came from so the error message
    is actionable without echoing the rejected value back to the caller.
    """
    candidate = raw.strip()
    if not _USER_ID_RE.match(candidate):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid {source} header. Expected 1-{MAX_USER_ID_LENGTH} "
                "characters from [A-Za-z0-9_-]."
            ),
        )
    return candidate


def resolve_user_id(
    authorization: Optional[str],
    x_user_id: Optional[str],
) -> Optional[str]:
    """Resolve the calling user's id, or ``None`` if no identity was sent.

    Pure function over the two header values — no FastAPI dependency
    machinery — so it can be unit-tested and reused directly.
    """
    # 1. Bearer token (future Firebase path).
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token.strip():
            verified = _verify_bearer_token(token.strip())
            if verified:
                return _validate_user_id(verified, "Authorization")
            # TODO(firebase): once _verify_bearer_token is implemented,
            # a present-but-unverifiable token should raise 401 here
            # instead of falling through to the X-User-Id header.

    # 2. Interim opaque id.
    if x_user_id and x_user_id.strip():
        return _validate_user_id(x_user_id, "X-User-Id")

    # 3. No identity supplied.
    return None


async def get_current_user_id(
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
) -> str:
    """FastAPI dependency returning the calling user's id.

    Every personalized endpoint depends on this and nothing else, so the
    Firebase migration is confined to ``_verify_bearer_token``.

    Raises 401 when no identity is supplied and
    ``settings.REQUIRE_USER_SCOPE`` is True.
    """
    user_id = resolve_user_id(authorization, x_user_id)
    if user_id:
        return user_id

    if settings.REQUIRE_USER_SCOPE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing user identity. Send an X-User-Id header.",
        )

    logger.warning(
        "Request without user identity; using the shared '%s' bucket. "
        "Set REQUIRE_USER_SCOPE=true to reject these.",
        ANONYMOUS_USER_ID,
    )
    return ANONYMOUS_USER_ID


async def get_optional_user_id(
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
) -> Optional[str]:
    """Like ``get_current_user_id`` but never raises.

    For endpoints that serve global data and merely *decorate* it with
    personalized fields when an identity happens to be present.
    """
    return resolve_user_id(authorization, x_user_id)
