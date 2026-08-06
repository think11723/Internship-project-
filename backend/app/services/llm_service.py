"""Sprint 9 — LLM service routed through the AIGateway.

The application no longer talks to OpenAI / OpenRouter / Groq /
Cerebras directly. Every LLM call goes through
``app.services.ai_gateway.get_gateway()``, which tries each
configured provider in priority order and falls back on
retryable failures.

Backward compatibility:
  - ``LLMService()`` constructor accepts no arguments (settings are
    read from the gateway, not from env directly).
  - ``LLMService.generate_cover_letter(candidate, company,
    extra_context="")`` is the public method the cover-letter route
    already calls. It still works.
  - The ``client`` attribute is preserved for any code that imports
    it directly. It is a ``AIGateway`` instance, not an OpenAI
    client. The two objects share a small surface (``.chat``,
    ``.completions``), but callers that relied on OpenAI-specific
    methods should be migrated to use ``AIGateway`` directly.

If the gateway returns ``None`` (every provider failed or none
configured), the cover-letter endpoint returns 503 — exactly the
same behaviour as the previous OpenRouter failure path.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.services.ai_gateway import AIGateway, get_gateway

logger = logging.getLogger("fundflow.llm_service")


class LLMService:
    """LLM service routed through the AIGateway.

    Two public methods:
      - ``generate_cover_letter(candidate, company, extra_context="")``
        returns the body of a personalised cover letter, or ``None``
        if every provider failed.
      - ``client``: the underlying ``AIGateway`` instance, exposed for
        callers that need bespoke prompts (e.g. the weekly discovery
        enrichment path).
    """

    def __init__(self) -> None:
        # Lazily build the gateway (only the first time it's needed).
        # The application may set the provider order at runtime via
        # ``get_gateway().set_enabled(name, bool)``.
        self.client: AIGateway = get_gateway()

    def generate_cover_letter(
        self,
        candidate: Dict[str, Any],
        company: Dict[str, Any],
        extra_context: str = "",
    ) -> Optional[str]:
        """Generate a personalised cover letter via the AIGateway.

        Args:
            candidate: Candidate profile dict (name, summary, skills, ...).
            company: Target company dict (name, tagline, industry, ...).
            extra_context: Optional Sprint 8 context string built by
                ``application_package.build_application_package``.

        Returns:
            The cover letter body as plain text, or ``None`` if every
            provider failed or the gateway is not configured.
        """
        prompt = self._build_cover_letter_prompt(
            candidate, company, extra_context
        )
        try:
            content = self.client.generate(prompt)
        except Exception as exc:  # defensive — gateway already swallows
            logger.error("Cover letter gateway call failed: %s", exc)
            return None
        if not content:
            logger.warning(
                "Cover letter generation returned empty content "
                "(gateway returned None or empty)"
            )
            return None
        return content.strip()

    def _build_cover_letter_prompt(
        self,
        candidate: Dict[str, Any],
        company: Dict[str, Any],
        extra_context: str = "",
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

        prompt = f"""You are a professional career writer helping a candidate write a personalized cover letter.

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

        if extra_context:
            prompt += "\n\n" + extra_context

        return prompt
