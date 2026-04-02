"""Robust JSON extraction from LLM output."""

import json
import re
import logging

logger = logging.getLogger(__name__)


def parse_llm_json(response: str) -> dict | list:
    """Extract JSON from LLM response, handling markdown fences and extra text."""
    if not response or not response.strip():
        return {}

    text = response.strip()

    # Strip markdown code fences
    text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find first [ or { and parse from there
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        start = text.find(start_char)
        if start == -1:
            continue
        end = text.rfind(end_char)
        if end == -1 or end <= start:
            continue
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            continue

    logger.warning("Failed to parse JSON from LLM response: %s...", text[:100])
    return {}
