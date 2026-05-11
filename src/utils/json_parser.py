"""Robust JSON extraction from LLM output."""

import json
import re
import logging

logger = logging.getLogger(__name__)


def _try_repair_truncated(text: str) -> dict | list | None:
    """Attempt to repair JSON truncated by token limits.

    Walks the string to find the outermost opening brace/bracket, then
    progressively trims from the end and closes open structures until
    it parses.
    """
    start = -1
    for i, ch in enumerate(text):
        if ch in ('{', '['):
            start = i
            break
    if start == -1:
        return None

    candidate = text[start:]
    # Try trimming back to the last complete key-value or element
    for trim in range(min(500, len(candidate)), 0, -1):
        chunk = candidate[:len(candidate) - trim]
        # Remove trailing partial string/value
        chunk = re.sub(r',\s*"[^"]*$', '', chunk)
        chunk = re.sub(r',\s*$', '', chunk)
        # Count open braces/brackets
        opens = []
        in_string = False
        escape = False
        for ch in chunk:
            if escape:
                escape = False
                continue
            if ch == '\\' and in_string:
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch in ('{', '['):
                opens.append(ch)
            elif ch == '}' and opens and opens[-1] == '{':
                opens.pop()
            elif ch == ']' and opens and opens[-1] == '[':
                opens.pop()
        # Close remaining opens
        closers = ''.join('}' if o == '{' else ']' for o in reversed(opens))
        try:
            result = json.loads(chunk + closers)
            logger.info("Repaired truncated JSON (trimmed %d chars, closed %d brackets)", trim, len(opens))
            return result
        except json.JSONDecodeError:
            continue
    return None


def _find_balanced_json(text: str, open_char: str = "{", close_char: str = "}") -> str | None:
    """Find the first balanced JSON object/array in text using brace counting."""
    start = text.find(open_char)
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


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

    # Find first balanced JSON object or array
    for open_ch, close_ch in [("{", "}"), ("[", "]")]:
        balanced = _find_balanced_json(text, open_ch, close_ch)
        if balanced:
            try:
                return json.loads(balanced)
            except json.JSONDecodeError:
                continue

    # Fallback: find first { and last } (handles some edge cases)
    for start_char, end_char in [("{", "}"), ("[", "]")]:
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

    # Try to repair truncated JSON (e.g. from token limit)
    repaired = _try_repair_truncated(text)
    if repaired is not None:
        return repaired

    logger.warning("Failed to parse JSON from LLM response: %s...", text[:100])
    return {}
