"""
Global exception handlers for standardized error responses
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Optional
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException, RequestValidationError
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.schemas.resume import ErrorResponse, ValidationErrorResponse

logger = logging.getLogger("fundflow")


def setup_exception_handlers(app):
    """Register global exception handlers with the FastAPI app."""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Handle HTTPException with standardized error response."""
        request_id = str(uuid.uuid4())
        logger.warning(
            f"HTTP error (request_id={request_id}): {exc.status_code} - {exc.detail}",
            extra={"request_id": request_id, "path": request.url, "method": request.method}
        )

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "status": "error",
                "message": exc.detail,
                "error_code": f"HTTP_{exc.status_code}",
                "timestamp": datetime.utcnow().isoformat(),
                "request_id": request_id,
            }
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Handle Pydantic validation errors with standardized response."""
        request_id = str(uuid.uuid4())
        logger.warning(
            f"Validation error (request_id={request_id}): {exc.errors()}",
            extra={"request_id": request_id, "path": request.url, "method": request.method}
        )

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "status": "validation_error",
                "message": "Request validation failed",
                "errors": exc.errors(),
                "timestamp": datetime.utcnow().isoformat(),
                "request_id": request_id,
            }
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_exception_handler(request: Request, exc: SQLAlchemyError):
        """Handle database errors with standardized response."""
        request_id = str(uuid.uuid4())
        logger.error(
            f"Database error (request_id={request_id}): {exc}",
            extra={"request_id": request_id, "path": request.url, "method": request.method}
        )

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "status": "error",
                "message": "Database operation failed",
                "error_code": "DATABASE_ERROR",
                "timestamp": datetime.utcnow().isoformat(),
                "request_id": request_id,
            }
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        """Handle ValueError with standardized response."""
        request_id = str(uuid.uuid4())
        logger.warning(
            f"Value error (request_id={request_id}): {exc}",
            extra={"request_id": request_id, "path": request.url, "method": request.method}
        )

        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "status": "error",
                "message": str(exc),
                "error_code": "VALUE_ERROR",
                "timestamp": datetime.utcnow().isoformat(),
                "request_id": request_id,
            }
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle all other exceptions with standardized response."""
        request_id = str(uuid.uuid4())
        logger.error(
            f"Unexpected error (request_id={request_id}): {exc}",
            extra={"request_id": request_id, "path": request.url, "method": request.method},
            exc_info=True
        )

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "status": "error",
                "message": "An unexpected error occurred",
                "error_code": "INTERNAL_ERROR",
                "timestamp": datetime.utcnow().isoformat(),
                "request_id": request_id,
            }
        )
