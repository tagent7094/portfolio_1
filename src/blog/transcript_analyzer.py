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

    founder_name = state.founder_slug.replace("_", " ").title()

    beliefs = state.founder_ctx.get("beliefs", [])[:10]
    beliefs_summary = "\n".join(
        f"- {b.get('topic', '')}: {b.get('stance', '')}" for b in beliefs
    )

    # Truncate transcript to fit context window
    transcript = state.transcript_text[:15000]
    if len(state.transcript_text) > 15000:
        logger.info("[narrative] Truncated transcript from %d to 15000 chars", len(state.transcript_text))

    template = load_prompt(PROMPTS_DIR / "transcript_analysis.txt")
    prompt = fill_prompt(
        template,
        transcript_text=transcript,
        founder_name=founder_name,
        beliefs_summary=beliefs_summary,
        personality_card=state.personality_card[:2000],
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
    """Cross-reference transcript themes with founder graph to find narrative angles."""
    if getattr(state, "llm_router", None):
        llm = state.llm_router.for_task("narrative_mining")

    themes = transcript_analysis.get("themes", [])
    themes_str = "\n".join(
        f"- {t.get('theme', '')}: {t.get('summary', '')} (strength: {t.get('strength', 'medium')})"
        for t in themes if isinstance(t, dict)
    )

    quotes = transcript_analysis.get("quotes", [])
    for t in themes:
        if isinstance(t, dict):
            related_quotes = [
                q.get("text", "") for q in quotes
                if isinstance(q, dict) and q.get("usability") == "high"
            ][:3]
            t["key_quotes"] = related_quotes

    beliefs = state.founder_ctx.get("beliefs", [])[:10]
    beliefs_str = "\n".join(
        f"- [{b.get('node_id', '')}] {b.get('topic', '')}: {b.get('stance', '')}"
        for b in beliefs
    )

    stories = state.founder_ctx.get("stories", [])[:10]
    stories_str = "\n".join(
        f"- [{s.get('node_id', '')}] {s.get('title', '')}: {s.get('summary', '')}"
        for s in stories
    )

    contrast_pairs = state.founder_ctx.get("contrast_pairs", [])[:5]
    contrasts_str = "\n".join(
        f"- {c.get('left', '')} vs {c.get('right', '')}: {c.get('description', '')}"
        for c in contrast_pairs
    )

    template = load_prompt(PROMPTS_DIR / "narrative_mining.txt")
    prompt = fill_prompt(
        template,
        transcript_themes=themes_str or "(no themes extracted)",
        beliefs=beliefs_str or "Not documented",
        stories=stories_str or "Not documented",
        contrast_pairs=contrasts_str or "Not documented",
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
            a.setdefault("related_beliefs", [])
            a.setdefault("related_stories", [])

    angles.sort(key=lambda a: a.get("confidence", 0) if isinstance(a, dict) else 0, reverse=True)
    state.narrative_angles = angles
    return angles
