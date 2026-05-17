"""Narrative Extraction Protocol — extracts paradigm-level insights from podcast transcripts."""

from __future__ import annotations

import logging
from pathlib import Path

from ..utils.json_parser import parse_llm_json
from ..utils.text_utils import load_prompt, fill_prompt
from ..llm.base import LLMProvider
from .state import NarrativeState

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).parent / "prompts"


def extract_narratives(llm: LLMProvider, state: NarrativeState) -> dict:
    """Run the Narrative Extraction Protocol on transcript content.

    Returns dict with 'narratives' list (each has title, first_order through
    fifth_order, kills, quotable_line) and 'total_extracted' count.
    """
    if getattr(state, "llm_router", None):
        llm = state.llm_router.for_task("narrative_extraction")

    beliefs = state.founder_ctx.get("beliefs", [])[:5] if state.founder_ctx else []
    niche_parts = [b.get("topic", "") for b in beliefs if b.get("topic")]
    founder_niche = ", ".join(niche_parts[:3]) if niche_parts else "technology, startups"

    template = load_prompt(PROMPTS_DIR / "narrative_extraction.txt")
    prompt = fill_prompt(
        template,
        transcript_text=state.transcript_text,
        founder_niche=founder_niche,
    )

    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=0.4, max_tokens=llm.max_output_tokens)
    _dur = int((_t.time() - _start) * 1000)

    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage="narrative_extraction",
            template="narrative_extraction.txt",
            prompt=prompt,
            response=response,
            temperature=0.4,
            max_tokens=llm.max_output_tokens,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
            metadata={"transcript_length": len(state.transcript_text)},
        )

    if not isinstance(result, dict):
        result = {"narratives": [], "total_extracted": 0, "quality_note": ""}

    narratives = result.get("narratives", [])
    for n in narratives:
        if isinstance(n, dict):
            n.setdefault("title", "Untitled")
            n.setdefault("first_order", "")
            n.setdefault("second_order", "")
            n.setdefault("third_order", "")
            n.setdefault("fourth_order", "")
            n.setdefault("fifth_order", "")
            n.setdefault("kills", "")
            n.setdefault("quotable_line", "")

    result["narratives"] = narratives
    result.setdefault("total_extracted", len(narratives))
    state.extracted_narratives = narratives
    return result
