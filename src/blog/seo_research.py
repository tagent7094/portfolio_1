"""SEO keyword research and SERP analysis — runs before outline generation."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..utils.json_parser import parse_llm_json
from ..utils.text_utils import load_prompt, fill_prompt
from ..llm.base import LLMProvider
from .state import BlogState

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).parent / "prompts"


def keyword_research(llm: LLMProvider, state: BlogState) -> dict:
    """Run SEO keyword research for the blog topic."""
    if getattr(state, "llm_router", None):
        llm = state.llm_router.for_task("keyword_research")

    beliefs = state.founder_ctx.get("beliefs", [])[:5]
    niche_parts = [b.get("topic", "") for b in beliefs if b.get("topic")]
    founder_niche = ", ".join(niche_parts[:3]) if niche_parts else "technology, startups"

    personality_card = state.personality_card[:3000] if state.personality_card else "(not available)"
    target_audience = "B2B professionals, founders, industry practitioners"

    template = load_prompt(PROMPTS_DIR / "keyword_research.txt")
    prompt = fill_prompt(
        template,
        topic=state.topic,
        personality_card=personality_card,
        founder_niche=founder_niche,
        target_audience=target_audience,
    )

    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=0.3, max_tokens=3000)
    _dur = int((_t.time() - _start) * 1000)

    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage="keyword_research",
            template="keyword_research.txt",
            prompt=prompt,
            response=response,
            temperature=0.3,
            max_tokens=3000,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
            metadata={"topic": state.topic},
        )

    if not isinstance(result, dict):
        result = _fallback_seo_inputs(state.topic)

    result.setdefault("primary_keyword", state.topic)
    result.setdefault("long_tail_variations", [])
    result.setdefault("related_entities", [])
    result.setdefault("search_intent", "informational")
    result.setdefault("people_also_ask_targets", [])
    result.setdefault("competition", {})
    result.setdefault("founder_owned_angle", "")

    state.seo_inputs = result
    return result


def serp_analysis(llm: LLMProvider, state: BlogState) -> dict:
    """Analyze SERP competition for the primary keyword."""
    if getattr(state, "llm_router", None):
        llm = state.llm_router.for_task("serp_analysis")

    seo = state.seo_inputs
    competition = seo.get("competition", {})

    related_entities = seo.get("related_entities", [])
    entities_str = ", ".join(related_entities) if related_entities else "(none)"

    template = load_prompt(PROMPTS_DIR / "serp_analysis.txt")
    prompt = fill_prompt(
        template,
        primary_keyword=seo.get("primary_keyword", state.topic),
        search_intent=seo.get("search_intent", "informational"),
        related_entities=entities_str,
        founder_owned_angle=seo.get("founder_owned_angle", "(not determined)"),
        recommended_word_count_min=str(competition.get("recommended_word_count_min", 1500)),
        recommended_word_count_max=str(competition.get("recommended_word_count_max", 3000)),
    )

    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=0.3, max_tokens=3000)
    _dur = int((_t.time() - _start) * 1000)

    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage="serp_analysis",
            template="serp_analysis.txt",
            prompt=prompt,
            response=response,
            temperature=0.3,
            max_tokens=3000,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
            metadata={"primary_keyword": seo.get("primary_keyword", "")},
        )

    if not isinstance(result, dict):
        result = _fallback_serp(state.topic)

    result.setdefault("table_stakes", [])
    result.setdefault("required_structural_elements", [])
    result.setdefault("content_gaps_to_exploit", [])
    result.setdefault("recommended_format", "long_form_guide")
    result.setdefault("recommended_word_count", state.target_words[1])

    state.serp_competition = result
    return result


def format_seo_for_prompt(state: BlogState) -> dict:
    """Extract formatted SEO strings for downstream prompt injection."""
    seo = state.seo_inputs
    serp = state.serp_competition

    long_tails = seo.get("long_tail_variations", [])
    if long_tails and isinstance(long_tails[0], dict):
        lt_str = ", ".join(lt.get("phrase", "") for lt in long_tails)
    else:
        lt_str = ", ".join(str(lt) for lt in long_tails)

    entities = seo.get("related_entities", [])
    entities_str = ", ".join(str(e) for e in entities)

    paa = seo.get("people_also_ask_targets", [])
    paa_str = "\n".join(f"- {q}" for q in paa)

    gaps = serp.get("content_gaps_to_exploit", [])
    if gaps and isinstance(gaps[0], dict):
        gaps_str = "\n".join(f"- {g.get('gap', '')}" for g in gaps)
    else:
        gaps_str = "\n".join(f"- {g}" for g in gaps)

    table_stakes = serp.get("table_stakes", [])
    table_stakes_str = "\n".join(f"- {s}" for s in table_stakes)

    structural = serp.get("required_structural_elements", [])
    structural_str = ", ".join(str(s) for s in structural)

    unique_angle = serp.get("unique_owned_angle_refined", {})
    if isinstance(unique_angle, dict):
        unique_str = unique_angle.get("angle_statement", seo.get("founder_owned_angle", ""))
    else:
        unique_str = str(unique_angle)

    return {
        "primary_keyword": seo.get("primary_keyword", ""),
        "long_tail_variations": lt_str,
        "related_entities": entities_str,
        "search_intent": seo.get("search_intent", "informational"),
        "paa_targets": paa_str,
        "founder_owned_angle": seo.get("founder_owned_angle", ""),
        "recommended_format": serp.get("recommended_format", "long_form_guide"),
        "required_structural_elements": structural_str,
        "content_gaps": gaps_str,
        "table_stakes": table_stakes_str,
        "unique_angle": unique_str,
        "target_min": str(serp.get("recommended_word_count", 1500) - 300),
        "target_max": str(serp.get("recommended_word_count", 2500) + 500),
    }


def _fallback_seo_inputs(topic: str) -> dict:
    return {
        "primary_keyword": topic.lower(),
        "long_tail_variations": [],
        "related_entities": [],
        "search_intent": "informational",
        "people_also_ask_targets": [],
        "competition": {
            "recommended_word_count_min": 1500,
            "recommended_word_count_max": 3000,
        },
        "founder_owned_angle": "",
    }


def _fallback_serp(topic: str) -> dict:
    return {
        "table_stakes": [],
        "required_structural_elements": ["faq_section", "bulleted_list"],
        "content_gaps_to_exploit": [],
        "recommended_format": "long_form_guide",
        "recommended_word_count": 2500,
    }
