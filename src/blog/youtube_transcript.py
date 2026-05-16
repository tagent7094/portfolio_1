"""YouTube transcript extraction + LLM structuring for Content Studio."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from ..utils.json_parser import parse_llm_json
from ..utils.text_utils import load_prompt, fill_prompt

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).parent / "prompts"

_YT_PATTERNS = [
    re.compile(r'(?:youtube\.com/watch\?.*v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})'),
]


def _parse_video_id(url: str) -> str | None:
    for pat in _YT_PATTERNS:
        m = pat.search(url)
        if m:
            return m.group(1)
    return None


def extract_youtube_transcript(url: str) -> dict:
    """Extract raw transcript from a YouTube video URL.

    Returns {text, language, video_id, error}.
    Compatible with youtube-transcript-api >= 1.0.
    """
    video_id = _parse_video_id(url)
    if not video_id:
        return {"text": "", "language": "", "video_id": "", "error": f"Could not parse video ID from: {url}"}

    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return {"text": "", "language": "", "video_id": video_id, "error": "youtube-transcript-api not installed"}

    try:
        api = YouTubeTranscriptApi()

        language = "en"
        try:
            result = api.fetch(video_id, languages=["en"])
        except Exception:
            transcript_list = api.list(video_id)
            available = list(transcript_list)
            if not available:
                return {"text": "", "language": "", "video_id": video_id,
                        "error": "No transcripts available for this video"}
            language = available[0].language_code
            result = available[0].fetch()

        text_parts = []
        for snippet in result:
            line = snippet.text if hasattr(snippet, "text") else str(snippet)
            if line:
                text_parts.append(line)

        full_text = " ".join(text_parts)
        full_text = re.sub(r'\s+', ' ', full_text).strip()

        return {
            "text": full_text,
            "language": language,
            "video_id": video_id,
            "error": "",
        }
    except Exception as e:
        logger.warning("[youtube] transcript extraction failed for %s: %s", video_id, e)
        return {"text": "", "language": "", "video_id": video_id, "error": str(e)}


def structure_transcript(raw_text: str, language: str, video_id: str, llm) -> dict:
    """Pass raw transcript through an LLM to produce well-structured JSON.

    Args:
        raw_text: Raw caption text from YouTube
        language: Detected language code
        video_id: YouTube video ID
        llm: An LLMProvider instance (typically a light model like Haiku)

    Returns structured dict with segments, speakers, key_quotes, summary.
    """
    # Truncate to fit context — raw transcripts can be very long
    max_chars = 80_000
    truncated = raw_text[:max_chars]
    if len(raw_text) > max_chars:
        truncated += "\n\n[TRANSCRIPT TRUNCATED — original was longer]"

    template = load_prompt(PROMPTS_DIR / "transcript_structure.txt")
    prompt = fill_prompt(
        template,
        raw_transcript=truncated,
        language=language,
        video_id=video_id,
    )

    out_tokens = max(llm.max_output_tokens, 16000)

    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=0.2, max_tokens=out_tokens)
    _dur = int((_t.time() - _start) * 1000)
    logger.info("[youtube] structured transcript for %s in %dms (%d chars -> %d chars)",
                video_id, _dur, len(raw_text), len(response))

    result = parse_llm_json(response)
    if not isinstance(result, dict) or "segments" not in result:
        logger.warning("[youtube] structure_transcript parse failed, returning raw wrapper")
        return {
            "title": f"YouTube {video_id}",
            "language": language,
            "speakers": [],
            "segments": [{"topic": "Full transcript", "speaker": "Unknown", "text": raw_text}],
            "key_quotes": [],
            "summary": "",
            "structured": False,
        }

    result["structured"] = True
    return result


def structured_text_from_result(structured: dict) -> str:
    """Convert structured JSON back to readable plain text for storage."""
    parts = []
    if structured.get("title"):
        parts.append(f"# {structured['title']}\n")
    if structured.get("summary"):
        parts.append(f"Summary: {structured['summary']}\n")
    for seg in structured.get("segments", []):
        speaker = seg.get("speaker", "")
        topic = seg.get("topic", "")
        header = f"[{topic}]" if topic else ""
        if speaker:
            header = f"{speaker} {header}" if header else speaker
        if header:
            parts.append(f"\n## {header}")
        parts.append(seg.get("text", ""))
    if structured.get("key_quotes"):
        parts.append("\n## Key Quotes")
        for q in structured["key_quotes"]:
            parts.append(f'> "{q}"')
    return "\n\n".join(parts)
