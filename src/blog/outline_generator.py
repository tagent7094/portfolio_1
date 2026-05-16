"""Blog outline generation — creates structured blog skeleton from topic + founder context."""

from __future__ import annotations

import logging
from pathlib import Path

from ..utils.json_parser import parse_llm_json
from ..utils.text_utils import load_prompt, fill_prompt
from ..llm.base import LLMProvider
from .state import BlogState

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).parent / "prompts"


def generate_outline(llm: LLMProvider, state: BlogState) -> dict:
    """Generate a structured blog outline from topic + founder context."""
    if getattr(state, "llm_router", None):
        llm = state.llm_router.for_task("blog_outline")

    beliefs = state.founder_ctx.get("beliefs", [])
    topic_beliefs = [b for b in beliefs if _topic_match(b, state.topic)][:5]
    if not topic_beliefs:
        topic_beliefs = beliefs[:5]

    stories = state.founder_ctx.get("stories", [])
    topic_stories = [s for s in stories if _topic_match(s, state.topic)][:3]
    if not topic_stories:
        topic_stories = stories[:3]

    style_rules = state.founder_ctx.get("style_rules", [])
    vocabulary = state.founder_ctx.get("vocabulary", {})

    source_docs = (state.source_documents_text or "")[:10000]
    if not source_docs:
        source_docs = "(none provided)"

    template = load_prompt(PROMPTS_DIR / "outline_generation.txt")
    prompt = fill_prompt(
        template,
        topic=state.topic,
        tone=state.tone,
        target_words=str(state.target_words[1]),
        beliefs="\n".join(
            f"- {b.get('topic', '')}: {b.get('stance', '')}" for b in topic_beliefs
        ),
        stories="\n".join(
            f"- {s.get('title', '')}: {s.get('summary', '')}" for s in topic_stories
        ),
        voice_markers="\n".join(f"- {m}" for m in state.voice_markers),
        style_rules="\n".join(
            f"- {r.get('description', '')}" for r in style_rules[:10]
        ) or "Not documented",
        vocabulary=_format_vocabulary(vocabulary),
        custom_instructions=state.custom_instructions or "(none)",
        source_documents=source_docs,
    )

    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=0.4, max_tokens=2000)
    _dur = int((_t.time() - _start) * 1000)

    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage="blog_outline",
            template="outline_generation.txt",
            prompt=prompt,
            response=response,
            temperature=0.4,
            max_tokens=2000,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
            metadata={"topic": state.topic, "tone": state.tone},
        )

    if not isinstance(result, dict):
        logger.warning("[blog] Outline parse failed, using fallback")
        result = _fallback_outline(state)

    result.setdefault("title", state.topic)
    result.setdefault("sections", [])
    result.setdefault("intro_hook", "")
    result.setdefault("conclusion_cta", "")

    state.outline = result
    return result


def _topic_match(node: dict, topic: str) -> bool:
    topic_lower = topic.lower()
    node_topic = (node.get("topic", "") or node.get("title", "")).lower()
    stance = (node.get("stance", "") or node.get("summary", "")).lower()
    return any(
        word in node_topic or word in stance
        for word in topic_lower.split()
        if len(word) > 3
    )


def _format_vocabulary(vocab: dict) -> str:
    parts = []
    if vocab.get("phrases_used"):
        parts.append("USE: " + ", ".join(vocab["phrases_used"][:10]))
    if vocab.get("phrases_never"):
        parts.append("NEVER USE: " + ", ".join(vocab["phrases_never"][:10]))
    return "\n".join(parts) if parts else "Not documented"


def _fallback_outline(state: BlogState) -> dict:
    target = state.target_words[1]
    section_words = target // 4
    return {
        "title": state.topic,
        "intro_hook": "",
        "sections": [
            {"heading": "The Problem", "key_points": [], "beliefs_used": [], "stories_used": [], "target_words": section_words},
            {"heading": "The Insight", "key_points": [], "beliefs_used": [], "stories_used": [], "target_words": section_words},
            {"heading": "The Path Forward", "key_points": [], "beliefs_used": [], "stories_used": [], "target_words": section_words},
        ],
        "conclusion_cta": "",
    }
