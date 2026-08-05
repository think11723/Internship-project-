"""
Validation middleware for request validation
"""

import re
from typing import Any
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse


class ValidationMiddleware:
    """Centralized validation middleware for incoming requests."""

    def __init__(self, app):
        self.app = app
        self.app.middleware("http")(self.validate_request)

    async def validate_request(self, request: Request, call_next):
        """Validate request before it reaches the route handler."""
        # Validate query parameters (does not consume the request body)
        self._validate_query_params(request)

        response = await call_next(request)
        return response

    def _validate_json_body(self, body: Any) -> None:
        """Validate JSON body for potential malicious content."""
        if not isinstance(body, dict):
            return

        # Check for suspiciously large payloads
        body_str = str(body)
        if len(body_str) > 10_000_000:  # 10MB limit
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Request body too large"
            )

        # Check for nested object depth (prevent DoS)
        depth = self._get_json_depth(body)
        if depth > 20:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Request body structure too complex"
            )

    def _validate_query_params(self, request: Request) -> None:
        """Validate query parameters for potential injection."""
        for key, value in request.query_params.items():
            if not isinstance(value, str):
                continue

            # Check for SQL injection patterns
            sql_patterns = [
                r"(?i)\b(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|UNION|EXEC)\b",
                r"(?i)\b(OR|AND|XOR|NOT)\s+\d+\s*=\s*\d+",
                r"(?i)\b(--|;|\/\*|xp_|sp_)",
            ]
            for pattern in sql_patterns:
                if re.search(pattern, value):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid parameter: {key}"
                    )

            # Check for command injection patterns
            cmd_patterns = [
                r"(?i)[;&|`$]\s*(?:curl|wget|nc|bash|sh|powershell|cmd|exec)",
                r"(?i)\.\.(?:/|\\)",
            ]
            for pattern in cmd_patterns:
                if re.search(pattern, value):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid parameter: {key}"
                    )

    def _get_json_depth(self, obj: Any, current_depth: int = 0) -> int:
        """Calculate maximum depth of JSON object."""
        if current_depth > 20:
            return current_depth

        if isinstance(obj, dict):
            return max((self._get_json_depth(v, current_depth + 1) for v in obj.values()), default=current_depth)
        if isinstance(obj, list):
            return max((self._get_json_depth(item, current_depth + 1) for item in obj), default=current_depth)
        return current_depth


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal attacks."""
    # Remove path separators
    filename = filename.replace("/", "").replace("\\", "").replace("..", "")
    
    # Remove null bytes
    filename = filename.replace("\x00", "")
    
    # Keep only safe characters
    filename = re.sub(r"[^a-zA-Z0-9._-]", "", filename)
    
    # Limit length
    if len(filename) > 255:
        filename = filename[:255]
    
    return filename or "resume.pdf"


def validate_mime_type(content_type: str, filename: str) -> bool:
    """Validate MIME type against filename extension."""
    if not content_type:
        return False

    # Map of allowed MIME types to extensions
    allowed_mime_types = {
        "application/pdf": [".pdf"],
    }

    # Get extension from filename
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    allowed_extensions = allowed_mime_types.get(content_type, [])

    return f".{ext}" in allowed_extensions
