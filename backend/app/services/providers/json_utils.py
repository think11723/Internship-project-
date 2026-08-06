"""JSON-mode helpers shared across providers."""
from __future__ import annotations

import json
import re
from typing import Any, Dict


def append_json_instruction(prompt: str, schema: Dict[str, Any]) -> str:
    """Append a JSON-output instruction to a prompt. Subclasses call
    this when they don't have native JSON mode.
    """
    schema_hint = (
        "Return a JSON object matching this schema (only the object, "
        "no prose, no markdown fences):\n"
        + json.dumps(schema, indent=2)
    )
    return f"{prompt}\n\n{schema_hint}"


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def parse_json_response(raw: str, schema: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Parse a JSON response from a provider, tolerating markdown
    fences and leading prose.

    Raises ``ValueError`` if no JSON object can be extracted.
    """
    if not raw:
        raise ValueError("empty response from provider")
    text = raw.strip()
    # Strip ```json ... ``` fences if present.
    m = _FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()
    # Try direct parse first.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fall back: find the first {...} block in the text.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as e:
            raise ValueError(f"could not parse JSON from response: {e}") from e
    raise ValueError("no JSON object found in response")
