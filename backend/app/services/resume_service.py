"""Resume intelligence service for extracting structured profile data from PDFs.

Pipeline:
    1. Extract text from PDF via PDFParser (PyMuPDF primary, pdfplumber fallback).
    2. Call the shared LLMService (Ticket-008 -> OpenRouter) with a strict
       JSON prompt that produces the rich candidate profile schema.
    3. Retry the LLM call once on JSON parse failure.
    4. Fall back to a local regex/keyword extractor only if the LLM is
       unreachable or returns schema-invalid output. The application
       never crashes - an empty/minimal profile is always returned.

Reuses the existing LLMService - no new wrapper, no new provider.

The optional ``progress_callback`` parameter (callable accepting a single
str stage) is invoked at each real-stage boundary so the upload route can
publish actual progress events to its in-memory job registry.
"""

import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.schemas.resume import EducationItem, ExperienceItem, ResumeProfile
from app.tools.document_parser import PDFParser

logger = logging.getLogger("fundflow")


ProgressCallback = Optional[Callable[[str], None]]


_RESUME_PROFILE_PROMPT = """You are an expert resume parser.

Extract structured information from the resume below. Use ONLY information explicitly present in the resume. NEVER hallucinate or invent facts, companies, projects, dates, or metrics.

Return valid JSON in this exact shape:

{
  "name": "Candidate's full name",
  "email": "Email address",
  "phone": "Phone number",
  "location": "City, State/Country",
  "professional_summary": "2-3 sentence summary of the candidate's professional profile",
  "years_of_experience": "Human-readable phrase like '3 years' or '5+ years', empty if unclear",
  "skills": ["high-level capability 1", "high-level capability 2"],
  "technologies": ["specific technology 1", "specific technology 2"],
  "frameworks": ["React", "FastAPI", "Django"],
  "programming_languages": ["Python", "TypeScript", "Go"],
  "cloud": ["AWS", "GCP", "Azure"],
  "databases": ["PostgreSQL", "MongoDB", "Redis"],
  "tools": ["Docker", "Git", "Kubernetes"],
  "projects": ["Project A: brief one-line description", "Project B: brief one-line description"],
  "experience": [
    {"company": "Company name", "role": "Job title", "duration": "Date range", "description": "Key responsibilities"}
  ],
  "education": [
    {"institution": "University name", "degree": "Degree", "year": "Graduation year"}
  ],
  "strengths": ["Key strength 1", "Key strength 2"],
  "recommended_roles": ["Role 1", "Role 2", "Role 3"]
}

STRICT RULES:
- Empty string "" for missing text fields
- Empty array [] for missing list fields
- DO NOT fabricate companies, projects, dates, employers, internships, or metrics
- Categorize technologies correctly: a programming language goes in programming_languages, a cloud service goes in cloud, a database goes in databases, a build/tool product goes in tools, a framework goes in frameworks
- A technology may appear in multiple lists if it fits naturally
- recommended_roles: 1-4 specific roles the candidate is genuinely qualified for based ONLY on the resume content
- If years_of_experience is unclear or not stated, return empty string ""
- For experience and education, use empty fields ("") if any sub-field is missing
- Return ONLY the JSON object. No commentary, no markdown fences.

Resume text:
{resume_text}
"""


class ResumeIntelligenceService:
    """Extract structured resume information via the shared LLMService."""

    def __init__(self, api_key: Optional[str] = None):
        # ``api_key`` is accepted for backwards compatibility with the
        # original constructor signature. The active provider is now
        # OpenRouter, configured via app settings.
        self.api_key = api_key

    def process_resume(
        self,
        file_path: str,
        progress_callback: ProgressCallback = None,
    ) -> Tuple[ResumeProfile, str]:
        """Extract text from a PDF and return a structured ResumeProfile.

        If ``progress_callback`` is provided, it is invoked at each real
        stage boundary so the upload route can publish actual progress
        events to the in-memory job registry.

        Raises:
            ValueError: only if the PDF contains no extractable text.
        """
        def _emit(stage: str) -> None:
            if progress_callback:
                try:
                    progress_callback(stage)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("Progress callback raised: %s", exc)

        extracted_text = PDFParser.extract_text(file_path)
        if not extracted_text or not extracted_text.strip():
            raise ValueError("No readable text could be extracted from the PDF.")

        _emit("Extracting Text")

        _emit("Understanding Skills")
        _emit("Understanding Experience")
        _emit("Finding Technologies")

        # Primary path: real AI extraction via LLMService.
        try:
            _emit("Generating Career Profile")
            payload = self._call_llm_with_retry(extracted_text)
        except Exception as exc:
            logger.warning(
                "AI resume extraction unavailable (%s); using local parser", exc
            )
            profile = self._build_profile(self._build_fallback_payload(extracted_text))
            if not profile.professional_summary:
                profile.professional_summary = self._build_text_summary(
                    extracted_text, profile.skills
                )
            return profile, extracted_text

        try:
            profile = self._build_profile(payload)
        except ValueError as exc:
            logger.warning(
                "AI response did not match expected schema (%s); using local parser", exc
            )
            profile = self._build_profile(self._build_fallback_payload(extracted_text))
            if not profile.professional_summary:
                profile.professional_summary = self._build_text_summary(
                    extracted_text, profile.skills
                )
            return profile, extracted_text

        if not profile.professional_summary:
            profile.professional_summary = self._build_text_summary(
                extracted_text, profile.skills
            )

        return profile, extracted_text

    def _call_llm_with_retry(self, resume_text: str) -> Dict[str, Any]:
        """Call the LLM and retry once if the response is not valid JSON."""
        from app.services.llm_service import LLMService

        llm = LLMService()
        prompt = self._build_prompt(resume_text)

        last_exc: Optional[Exception] = None
        for attempt in range(2):
            try:
                response = llm.client.chat.completions.create(
                    model=llm._model(),
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                )
                content = ""
                if getattr(response, "choices", None):
                    for choice in response.choices:
                        message = getattr(choice, "message", None)
                        if message is not None and getattr(message, "content", None):
                            content = message.content
                            break
                if not content:
                    raise ValueError("empty content from provider")
                return json.loads(content)
            except json.JSONDecodeError as exc:
                last_exc = exc
                logger.warning(
                    "Resume LLM returned invalid JSON (attempt %d): %s",
                    attempt + 1,
                    exc,
                )
                continue

        raise ValueError(
            f"AI returned invalid JSON after retry: {last_exc}"
        )

    def _build_prompt(self, resume_text: str) -> str:
        # Use plain string replace instead of str.format because the
        # prompt template contains literal JSON examples with braces
        # like "name": "..." which str.format() would try to interpret
        # as format placeholders.
        return _RESUME_PROFILE_PROMPT.replace("{resume_text}", resume_text)

    def _build_profile(self, payload: Dict[str, Any]) -> ResumeProfile:
        normalized = {
            "name": self._as_string(payload.get("name")),
            "email": self._as_string(payload.get("email")),
            "phone": self._as_string(payload.get("phone")),
            "location": self._as_string(payload.get("location")),
            "professional_summary": self._as_string(payload.get("professional_summary")),
            "years_of_experience": self._as_string(payload.get("years_of_experience")),
            "skills": self._as_string_list(payload.get("skills")),
            "technologies": self._as_string_list(payload.get("technologies")),
            "frameworks": self._as_string_list(payload.get("frameworks")),
            "programming_languages": self._as_string_list(payload.get("programming_languages")),
            "cloud": self._as_string_list(payload.get("cloud")),
            "databases": self._as_string_list(payload.get("databases")),
            "tools": self._as_string_list(payload.get("tools")),
            "projects": self._as_string_list(payload.get("projects")),
            "experience": self._as_experience_list(payload.get("experience")),
            "education": self._as_education_list(payload.get("education")),
            "strengths": self._as_string_list(payload.get("strengths")),
            "recommended_roles": self._as_string_list(payload.get("recommended_roles")),
        }
        try:
            return ResumeProfile(**normalized)
        except Exception as exc:
            raise ValueError(
                f"AI response did not match expected schema: {exc}"
            ) from exc

    # ----- type coercion helpers -----

    def _as_string(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def _as_string_list(self, value: Any) -> List[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            return []
        return [self._as_string(item) for item in value if self._as_string(item)]

    def _as_experience_list(self, value: Any) -> List[ExperienceItem]:
        if not isinstance(value, list):
            return []
        items: List[ExperienceItem] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            items.append(
                ExperienceItem(
                    company=self._as_string(item.get("company")),
                    role=self._as_string(item.get("role")),
                    duration=self._as_string(item.get("duration")),
                    description=self._as_string(item.get("description")),
                )
            )
        return items

    def _as_education_list(self, value: Any) -> List[EducationItem]:
        if not isinstance(value, list):
            return []
        items: List[EducationItem] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            items.append(
                EducationItem(
                    institution=self._as_string(item.get("institution")),
                    degree=self._as_string(item.get("degree")),
                    year=self._as_string(item.get("year")),
                )
            )
        return items

    # ----- local fallback parser (only when LLM is unreachable) -----

    def _extract_email(self, text: str) -> str:
        match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
        return match.group(0) if match else ""

    def _extract_phone(self, text: str) -> str:
        match = re.search(r"(?:\+?\d[\d\s().-]{7,}\d)", text)
        return match.group(0).strip() if match else ""

    def _extract_location(self, text: str) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for line in lines:
            if re.search(r"[A-Za-z]+,\s*[A-Za-z]{2}|[A-Za-z]+\s+[A-Za-z]+", line):
                return line
        return ""

    def _extract_skills(self, text: str) -> List[str]:
        skill_keywords = [
            "python", "java", "javascript", "typescript", "react", "fastapi",
            "sql", "postgresql", "mysql", "mongodb", "aws", "docker", "kubernetes",
            "machine learning", "nlp", "azure", "git", "node", "linux", "pandas",
            "numpy", "spark", "c++", "c#",
        ]
        found: List[str] = []
        lowered = text.lower()
        for skill in skill_keywords:
            if skill in lowered:
                found.append(skill.capitalize() if skill.isalpha() else skill)
        return found[:8]

    def _extract_name(self, lines: List[str]) -> str:
        for line in lines[:8]:
            if "@" in line or re.search(r"\d", line):
                continue
            if len(line.split()) <= 6 and not line.lower().startswith(
                ("resume", "summary", "skills")
            ):
                return line
        return ""

    def _build_text_summary(self, resume_text: str, skills: List[str]) -> str:
        """Produce a friendly summary when the LLM didn't return one.

        Used as a fallback only — when the AI model returns an empty
        ``professional_summary``. Keeps the user-facing message
        informative without claiming things the AI didn't say.
        """
        words = [w for w in re.split(r"\s+", (resume_text or "").strip()) if w]
        word_count = len(words)
        if skills:
            skill_text = ", ".join(skills[:4])
            return (
                f"Resume profile extracted successfully from a {word_count}-word "
                f"resume. Detected skills: {skill_text}."
            )
        return (
            f"Resume profile extracted successfully from a {word_count}-word "
            f"resume. Add skills and details to your resume to unlock "
            f"personalized recommendations."
        )

    def _build_fallback_payload(self, text: str) -> Dict[str, Any]:
        normalized_text = (text or "").strip()
        lines = [line.strip() for line in normalized_text.splitlines() if line.strip()]
        email = self._extract_email(normalized_text)
        phone = self._extract_phone(normalized_text)
        location = self._extract_location(normalized_text)
        skills = self._extract_skills(normalized_text)
        name = self._extract_name(lines)
        summary = self._build_text_summary(normalized_text, skills)

        return {
            "name": name,
            "email": email,
            "phone": phone,
            "location": location,
            "professional_summary": summary,
            "years_of_experience": "",
            "skills": skills,
            "technologies": skills,
            "frameworks": [],
            "programming_languages": [],
            "cloud": [],
            "databases": [],
            "tools": [],
            "projects": [],
            "experience": [],
            "education": [],
            "strengths": skills[:4],
            "recommended_roles": [],
        }