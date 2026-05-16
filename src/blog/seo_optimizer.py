"""SEO optimization — titles, meta descriptions, headings."""

from __future__ import annotations

import logging
from pathlib import Path

from ..utils.json_parser import parse_llm_json
from ..utils.text_utils import load_prompt, fill_prompt
from ..llm.base import LLMProvider
from .state import BlogState

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).parent / "prompts"


def optimize_seo(llm: LLMProvider, blog_text: str, state: BlogState) -> dict:
    """Generate SEO metadata for a blog post."""
    if getattr(state, "llm_router", None):
        llm = state.llm_router.for_task("blog_seo")

    founder_name = state.founder_slug.replace("_", " ").title()

    template = load_prompt(PROMPTS_DIR / "seo_optimize.txt")
    prompt = fill_prompt(
        template,
        blog_content=blog_text[:6000],
        topic=state.topic,
        founder_name=founder_name,
    )

    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=0.2, max_tokens=1500)
    _dur = int((_t.time() - _start) * 1000)

    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage="blog_seo",
            template="seo_optimize.txt",
            prompt=prompt,
            response=response,
            temperature=0.2,
            max_tokens=1500,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
            metadata={"topic": state.topic},
        )

    if not isinstance(result, dict):
        slug = state.topic.lower().replace(" ", "-")[:50]
        return {
            "seo_title": state.outline.get("title", state.topic),
            "meta_description": "",
            "slug": slug,
            "primary_keyword": state.topic,
            "secondary_keywords": [],
            "optimized_headings": [],
        }

    state.seo_data = result
    return result
