"""Transcript analysis and narrative mining — extracts publishable angles from podcast/call content."""

from __future__ import annotations

import logging
from pathlib import Path

from ..utils.json_parser import parse_llm_json
from ..utils.text_utils import load_prompt, fill_prompt
from ..llm.base import LLMProvider
from .state import NarrativeState
from .seo_research import format_seo_for_prompt

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).parent / "prompts"


def analyze_transcript(llm: LLMProvider, state: NarrativeState) -> dict:
    """Extract themes, quotes, stories, and contrarian positions from transcript."""
    if getattr(state, "llm_router", None):
        llm = state.llm_router.for_task("narrative_transcript_analysis")

    transcript = state.transcript_text

    beliefs = state.founder_ctx.get("beliefs", [])[:5] if state.founder_ctx else []
    niche_parts = [b.get("topic", "") for b in beliefs if b.get("topic")]
    founder_niche = ", ".join(niche_parts[:3]) if niche_parts else "technology, startups"

    template = load_prompt(PROMPTS_DIR / "transcript_analysis.txt")
    prompt = fill_prompt(
        template,
        transcript_text=transcript,
        founder_niche=founder_niche,
    )

    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=0.3, max_tokens=llm.max_output_tokens)
    _dur = int((_t.time() - _start) * 1000)

    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage="narrative_transcript_analysis",
            template="transcript_analysis.txt",
            prompt=prompt,
            response=response,
            temperature=0.3,
            max_tokens=llm.max_output_tokens,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
            metadata={"transcript_length": len(state.transcript_text)},
        )

    if not isinstance(result, dict):
        result = {"themes": [], "quotes": [], "stories": [], "contrarian_positions": [], "actionable_insights": []}

    return result


def mine_narratives(llm: LLMProvider, state: NarrativeState, transcript_analysis: dict) -> list[dict]:
    """Mine publishable narrative angles from transcript themes."""
    if getattr(state, "llm_router", None):
        llm = state.llm_router.for_task("narrative_mining")

    themes = transcript_analysis.get("themes", [])
    themes_str = "\n".join(
        f"- {t.get('theme', '')}: {t.get('summary', '')} (strength: {t.get('strength', 'medium')}, seo: {t.get('seo_potential', 'medium')})"
        for t in themes if isinstance(t, dict)
    )

    quotes = transcript_analysis.get("quotes", [])
    quotes_str = "\n".join(
        f'- "{q.get("text", "")}" (context: {q.get("context", "")})'
        for q in quotes if isinstance(q, dict) and q.get("usability") in ("high", "medium")
    )[:3000]

    contrarian = transcript_analysis.get("contrarian_positions", [])
    contrarian_str = "\n".join(
        f"- {c.get('position', '')} (vs: {c.get('conventional_wisdom', '')})"
        for c in contrarian if isinstance(c, dict)
    )

    searchable_qs = transcript_analysis.get("searchable_questions", [])
    searchable_str = "\n".join(f"- {q}" for q in searchable_qs)

    seo_vars = format_seo_for_prompt(state)

    template = load_prompt(PROMPTS_DIR / "narrative_mining.txt")
    prompt = fill_prompt(
        template,
        transcript_themes=themes_str or "(no themes extracted)",
        transcript_quotes=quotes_str or "(no quotes extracted)",
        contrarian_positions=contrarian_str or "(none identified)",
        searchable_questions=searchable_str or "(none identified)",
        primary_keyword=seo_vars["primary_keyword"],
        long_tail_variations=seo_vars["long_tail_variations"],
        search_intent=seo_vars["search_intent"],
        founder_owned_angle=seo_vars["founder_owned_angle"],
        recommended_format=seo_vars["recommended_format"],
        paa_targets=seo_vars["paa_targets"],
        table_stakes=seo_vars["table_stakes"],
        content_gaps=seo_vars["content_gaps"],
        unique_angle=seo_vars["unique_angle"],
    )

    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=0.3, max_tokens=llm.max_output_tokens)
    _dur = int((_t.time() - _start) * 1000)

    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage="narrative_mining",
            template="narrative_mining.txt",
            prompt=prompt,
            response=response,
            temperature=0.3,
            max_tokens=llm.max_output_tokens,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
            metadata={"themes_count": len(themes)},
        )

    angles = []
    if isinstance(result, dict) and "narrative_angles" in result:
        angles = result["narrative_angles"]
    elif isinstance(result, list):
        angles = result

    for a in angles:
        if isinstance(a, dict):
            a.setdefault("confidence", 0.5)
            a.setdefault("format_recommendation", "thought_leadership")
            a.setdefault("supporting_transcript_quotes", [])

    angles.sort(key=lambda a: a.get("confidence", 0) if isinstance(a, dict) else 0, reverse=True)
    state.narrative_angles = angles
    return angles
