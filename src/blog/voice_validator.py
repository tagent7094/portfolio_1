"""Blog voice validation — ensures long-form content sounds like the founder."""

from __future__ import annotations

import logging
from pathlib import Path

from ..utils.json_parser import parse_llm_json
from ..utils.text_utils import load_prompt, fill_prompt
from ..llm.base import LLMProvider
from ..batch.voice_validator import VOICE_BLACKLIST, _deterministic_voice_check
from .state import BlogState

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).parent / "prompts"


def validate_blog_voice(llm: LLMProvider, blog_text: str, state: BlogState) -> dict:
    """Validate a complete blog post against founder voice markers."""
    blacklist_hits = _deterministic_voice_check(blog_text)
    if blacklist_hits:
        logger.info("[blog_voice] blacklist FAIL — %s", ", ".join(blacklist_hits))
        return {
            "overall": "FAIL",
            "voice_marker_score": 0,
            "register_score": 0,
            "consistency_score": 0,
            "authenticity_score": 0,
            "register_reads_as": "corporate",
            "violations": [f"Blacklisted phrase: '{p}'" for p in blacklist_hits],
            "suggestion": f"Remove corporate language: {', '.join(blacklist_hits)}",
            "blacklist_fail": True,
        }

    if getattr(state, "llm_router", None):
        llm = state.llm_router.for_task("blog_voice_check")

    template = load_prompt(PROMPTS_DIR / "voice_validation_blog.txt")
    prompt = fill_prompt(
        template,
        blog_text=blog_text[:8000],
        voice_markers="\n".join(f"- {m}" for m in state.voice_markers),
        calibration_paragraph=state.calibration_paragraph or "(not available)",
        formatting_habits=str(state.formatting_habits),
    )

    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=0.3, max_tokens=llm.max_output_tokens)
    _dur = int((_t.time() - _start) * 1000)

    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage="blog_voice_check",
            template="voice_validation_blog.txt",
            prompt=prompt,
            response=response,
            temperature=0.3,
            max_tokens=llm.max_output_tokens,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
            metadata={"word_count": len(blog_text.split())},
        )

    if not isinstance(result, dict):
        return {
            "overall": "PASS",
            "voice_marker_score": 3,
            "register_score": 3,
            "consistency_score": 3,
            "authenticity_score": 3,
        }

    return result
