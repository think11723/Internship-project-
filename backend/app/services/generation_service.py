"""Cover letter generation service.

Wraps the existing LLMService to produce a personalized cover letter
for the candidate + a target company. Any failure (missing API key,
network error, empty response) is returned as None so the orchestrator
can continue rendering the rest of the report without crashing.
"""

import logging
from typing import Any, Dict, Optional

from app.services.llm_service import LLMService

logger = logging.getLogger("fundflow")


def generate_cover_letter(
    candidate: Dict[str, Any],
    company: Dict[str, Any],
) -> Optional[Dict[str, str]]:
    """Generate a personalized cover letter for a candidate + company pair.

    Returns a payload with the target company name and letter body on
    success. Returns None on any failure (missing API key, OpenAI
    network error, empty content, etc.) and logs the reason.
    """
    try:
        llm = LLMService()
    except Exception as exc:
        # Catches missing API key (ValueError) and any SDK / httpx
        # initialization errors (TypeError, ImportError, etc.).
        logger.error("Cover letter skipped: %s", exc)
        return None

    try:
        content = llm.generate_cover_letter(candidate, company)
    except Exception as exc:
        logger.error("Cover letter generation failed: %s", exc)
        return None

    if not content:
        logger.error("Cover letter generation returned empty content")
        return None

    return {
        "company": company.get("name", ""),
        "content": content,
    }