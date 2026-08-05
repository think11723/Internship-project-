"""LLM service backed by OpenRouter via the OpenAI SDK.

OpenRouter exposes an OpenAI-compatible API, so we reuse the official
``openai`` Python SDK and only change the transport configuration
(base_url, api_key, model). All public methods keep their original
signatures; only the network call has been migrated.
"""

import json
import logging
from typing import Any, Dict

import httpx
from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger("fundflow")


class LLMService:
    """LLM service routed through OpenRouter.

    Two public methods are exposed:

    - ``generate_cover_letter(candidate, company)``: produces a plain-text
      cover letter using a deterministic prompt built into this class.
    - ``client``: the raw OpenAI client, exposed for callers that need
      bespoke prompts and parsing (e.g. ``discovery_service`` for
      company normalization).
    """

    def __init__(self) -> None:
        """Initialize the OpenAI SDK pointed at OpenRouter.

        We pass a pre-built ``httpx.Client`` via the ``http_client``
        kwarg to avoid the legacy ``proxies=`` argument that
        ``openai==1.3.7`` passes internally and that ``httpx>=0.28``
        no longer accepts.

        Raises:
            ValueError: if ``OPENROUTER_API_KEY`` is not configured.
        """
        if not settings.OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY not configured")
        self.client = OpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            http_client=httpx.Client(timeout=180.0),
        )

    def _model(self) -> str:
        """Return the configured OpenRouter model name."""
        return settings.OPENROUTER_MODEL

    def generate_cover_letter(
        self,
        candidate: Dict[str, Any],
        company: Dict[str, Any],
    ) -> str:
        """Generate a personalized cover letter via OpenRouter.

        Args:
            candidate: Candidate profile dict (name, summary, skills, ...).
            company: Target company dict (name, tagline, industry, ...).

        Returns:
            The cover letter body as plain text.

        Raises:
            Exception: any underlying provider / network error, so
                callers can log and degrade gracefully.
        """
        prompt = self._build_cover_letter_prompt(candidate, company)

        try:
            response = self.client.chat.completions.create(
                model=self._model(),
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            logger.error("Cover letter OpenRouter call failed: %s", exc)
            raise

        content = ""
        for choice in getattr(response, "choices", []) or []:
            message = getattr(choice, "message", None)
            if message is not None and getattr(message, "content", None):
                content = message.content
                break

        if not content:
            logger.error("Cover letter generation returned empty content")
        return content.strip()

    def _build_cover_letter_prompt(
        self,
        candidate: Dict[str, Any],
        company: Dict[str, Any],
    ) -> str:
        """Build the cover-letter generation prompt.

        The prompt enforces:
        - Specific (not generic) language
        - Real skills referenced by name
        - No fabricated achievements, employers, or metrics
        - No markdown, headers, or placeholders
        - 250-350 words, plain text only
        """
        name = (candidate.get("name") or "").strip() or "the candidate"
        summary = (candidate.get("summary") or "").strip() or "(no summary provided)"
        skills_list = candidate.get("skills") or []
        top_skills = ", ".join(skills_list[:5]) if skills_list else "(no skills listed)"

        company_name = (company.get("name") or "").strip() or "the company"
        tagline = (company.get("tagline") or "").strip() or "(no tagline)"
        industry = (company.get("industry") or "").strip() or "(no industry)"

        return f"""You are a professional career writer helping a candidate write a personalized cover letter.

Write a cover letter for the candidate and target company below. The letter must be specific to this candidate and this company — never generic.

CANDIDATE
- Name: {name}
- Professional Summary: {summary}
- Top Skills: {top_skills}

TARGET COMPANY
- Name: {company_name}
- Tagline: {tagline}
- Industry: {industry}

STRICT REQUIREMENTS
- Length: 250-350 words
- Reference at least 2 specific skills from the candidate's profile by name
- Reference the company's tagline or industry with concrete detail (avoid generic praise like "I love your innovative culture")
- Do NOT fabricate any achievements, prior employers, projects, internships, or metrics
- Do NOT use markdown, bullet points, headers, or placeholder text
- Do NOT include a header block (no To/From/Date)
- Open with "Dear Hiring Team,"
- Close with "Sincerely," followed by the candidate's name on the next line
- Write in the candidate's own voice — natural and specific, not robotic

Return ONLY the letter body. No commentary, no labels, no code fences."""