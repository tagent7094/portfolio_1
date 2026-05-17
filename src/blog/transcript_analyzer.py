"""Transcript analysis and narrative mining — extracts publishable angles from podcast/call content."""

from __future__ import annotations

import logging
from pathlib import Path

from ..utils.json_parser import parse_llm_json
from ..utils.text_utils import load_prompt, fill_prompt
from ..llm.base import LLMProvider
from .state import NarrativeState

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).parent / "prompts"


def analyze_transcript(llm: LLMProvider, state: NarrativeState) -> dict:
    """Extract themes, quotes, stories, and contrarian positions from transcript."""
    if getattr(state, "llm_router", None):
        llm = state.llm_router.for_task("narrative_transcript_analysis")

    transcript = state.transcript_text

    template = load_prompt(PROMPTS_DIR / "transcript_analysis.txt")
    prompt = fill_prompt(
        template,
        transcript_text=transcript,
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
        f"- {t.get('theme', '')}: {t.get('summary', '')} (strength: {t.get('strength', 'medium')})"
        for t in themes if isinstance(t, dict)
    )

    quotes = transcript_analysis.get("quotes", [])
    quotes_str = "\n".join(
        f'- "{q.get("text", "")}" (context: {q.get("context", "")})'
        for q in quotes if isinstance(q, dict) and q.get("usability") in ("high", "medium")
    )[:3000]

    template = load_prompt(PROMPTS_DIR / "narrative_mining.txt")
    prompt = fill_prompt(
        template,
        transcript_themes=themes_str or "(no themes extracted)",
        transcript_quotes=quotes_str or "(no quotes extracted)",
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
