"""
Application logging configuration
"""

import logging
import sys
from pathlib import Path
from typing import Any
from app.core.config import settings


# Create global logger instance
logger = logging.getLogger("fundflow")


def setup_logging() -> logging.Logger:
    """Configure structured logging for the application."""
    
    # Create formatters
    formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)
    
    # File handler (if logs directory exists)
    logs_dir = Path("logs")
    if logs_dir.exists():
        file_handler = logging.FileHandler(logs_dir / "fundflow.log")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)
    root_logger.addHandler(console_handler)
    if logs_dir.exists():
        root_logger.addHandler(file_handler)
    
    # Set log levels for external libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    
    return root_logger


def log_performance(operation: str, duration_ms: float, metadata: dict = None):
    """Log performance metrics for key operations."""
    logger = logging.getLogger("fundflow.performance")
    logger.info(
        f"PERF: {operation} completed in {duration_ms:.2f}ms",
        extra={
            "operation": operation,
            "duration_ms": duration_ms,
            **(metadata or {})
        }
    )


def log_cache_hit(cache_type: str, key: str):
    """Log cache hit for monitoring."""
    logger = logging.getLogger("fundflow.cache")
    logger.debug(f"CACHE_HIT: {cache_type} - {key}")


def log_cache_miss(cache_type: str, key: str):
    """Log cache miss for monitoring."""
    logger = logging.getLogger("fundflow.cache")
    logger.debug(f"CACHE_MISS: {cache_type} - {key}")


def log_api_call(service: str, endpoint: str, duration_ms: float, success: bool):
    """Log external API call for monitoring."""
    logger = logging.getLogger("fundflow.api")
    status = "SUCCESS" if success else "FAILED"
    logger.info(
        f"API_CALL: {service} - {endpoint} - {status} - {duration_ms:.2f}ms",
        extra={
            "service": service,
            "endpoint": endpoint,
            "duration_ms": duration_ms,
            "success": success
        }
    )
