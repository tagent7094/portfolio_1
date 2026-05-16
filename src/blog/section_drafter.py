"""Section-by-section blog drafting — writes each section in founder voice."""

from __future__ import annotations

import logging
from pathlib import Path

from ..utils.json_parser import parse_llm_json
from ..utils.text_utils import load_prompt, fill_prompt
from ..llm.base import LLMProvider
from .state import BlogState, NarrativeState

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).parent / "prompts"


def draft_section(llm: LLMProvider, section: dict, section_idx: int,
                  state: BlogState, preceding_sections: list[str]) -> str:
    """Draft a single blog section in founder voice."""
    if getattr(state, "llm_router", None):
        llm = state.llm_router.for_task("blog_section_draft")

    preceding_summary = ""
    if preceding_sections:
        preceding_summary = "Previous sections covered:\n" + "\n".join(
            f"- {s[:200]}..." if len(s) > 200 else f"- {s}" for s in preceding_sections
        )

    beliefs = state.founder_ctx.get("beliefs", [])
    belief_ids = section.get("beliefs_used", [])
    supporting_beliefs = "\n".join(
        f"- {b.get('topic', '')}: {b.get('stance', '')}"
        for b in beliefs
        if b.get("node_id") in belief_ids or b.get("topic") in belief_ids
    ) or "Use relevant beliefs from the founder's worldview"

    stories = state.founder_ctx.get("stories", [])
    story_ids = section.get("stories_used", [])
    supporting_stories = "\n".join(
        f"- {s.get('title', '')}: {s.get('summary', '')}"
        for s in stories
        if s.get("node_id") in story_ids or s.get("title") in story_ids
    ) or "Draw on the founder's experience where relevant"

    vocabulary = state.founder_ctx.get("vocabulary", {})
    vocab_str = ""
    if vocabulary.get("phrases_used"):
        vocab_str += "USE: " + ", ".join(vocabulary["phrases_used"][:10]) + "\n"
    if vocabulary.get("phrases_never"):
        vocab_str += "NEVER USE: " + ", ".join(vocabulary["phrases_never"][:10])

    source_docs = (state.source_documents_text or "")[:10000]
    if not source_docs:
        source_docs = "(none provided)"

    template = load_prompt(PROMPTS_DIR / "section_draft.txt")
    prompt = fill_prompt(
        template,
        section_heading=section.get("heading", f"Section {section_idx + 1}"),
        section_context="\n".join(f"- {p}" for p in section.get("key_points", [])),
        word_target=str(section.get("target_words", 400)),
        preceding_summary=preceding_summary or "(this is the first section)",
        supporting_beliefs=supporting_beliefs,
        supporting_stories=supporting_stories,
        tone=state.tone,
        voice_markers="\n".join(f"- {m}" for m in state.voice_markers),
        calibration_paragraph=state.calibration_paragraph or "(not available)",
        formatting_habits=str(state.formatting_habits),
        vocabulary=vocab_str or "Not documented",
        custom_instructions=state.custom_instructions or "(none)",
        source_documents=source_docs,
    )

    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=0.5, max_tokens=4000)
    _dur = int((_t.time() - _start) * 1000)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage=f"blog_section_draft_{section_idx}",
            template="section_draft.txt",
            prompt=prompt,
            response=response,
            temperature=0.5,
            max_tokens=4000,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
            metadata={"heading": section.get("heading", ""), "section_idx": section_idx},
        )

    text = response.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    return text


def draft_narrative(llm: LLMProvider, state: NarrativeState) -> dict:
    """Generate a full blog post from a narrative angle using transcript content."""
    if getattr(state, "llm_router", None):
        llm = state.llm_router.for_task("narrative_draft")

    angle = state.selected_angle
    transcript_excerpts = "\n\n".join(
        f"> {q}" for q in angle.get("supporting_transcript_quotes", [])[:10]
    ) or state.transcript_text[:3000]

    beliefs = state.founder_ctx.get("beliefs", [])
    belief_ids = angle.get("related_beliefs", [])
    beliefs_str = "\n".join(
        f"- {b.get('topic', '')}: {b.get('stance', '')}"
        for b in beliefs
        if b.get("node_id") in belief_ids or b.get("topic") in belief_ids
    ) or "\n".join(f"- {b.get('topic', '')}: {b.get('stance', '')}" for b in beliefs[:5])

    stories = state.founder_ctx.get("stories", [])
    story_ids = angle.get("related_stories", [])
    stories_str = "\n".join(
        f"- {s.get('title', '')}: {s.get('summary', '')}"
        for s in stories
        if s.get("node_id") in story_ids or s.get("title") in story_ids
    ) or "\n".join(f"- {s.get('title', '')}: {s.get('summary', '')}" for s in stories[:3])

    vocabulary = state.founder_ctx.get("vocabulary", {})
    vocab_str = ""
    if vocabulary.get("phrases_used"):
        vocab_str += "USE: " + ", ".join(vocabulary["phrases_used"][:10]) + "\n"
    if vocabulary.get("phrases_never"):
        vocab_str += "NEVER USE: " + ", ".join(vocabulary["phrases_never"][:10])

    template = load_prompt(PROMPTS_DIR / "narrative_draft.txt")
    prompt = fill_prompt(
        template,
        narrative_angle=angle.get("angle", state.topic),
        format_type=state.format_type,
        tone=state.tone,
        target_words=str(state.target_words[1]),
        transcript_excerpts=transcript_excerpts,
        custom_instructions=state.custom_instructions or "(none)",
        voice_markers="\n".join(f"- {m}" for m in state.voice_markers),
        calibration_paragraph=state.calibration_paragraph or "(not available)",
        formatting_habits=str(state.formatting_habits),
        vocabulary=vocab_str or "Not documented",
        beliefs=beliefs_str,
        stories=stories_str,
    )

    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=0.5, max_tokens=llm.max_output_tokens)
    _dur = int((_t.time() - _start) * 1000)

    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage="narrative_draft",
            template="narrative_draft.txt",
            prompt=prompt,
            response=response,
            temperature=0.5,
            max_tokens=llm.max_output_tokens,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
            metadata={"format_type": state.format_type, "angle": angle.get("angle", "")},
        )

    if isinstance(result, dict) and result.get("content"):
        return result

    return {
        "title": state.topic,
        "content": response.strip(),
        "word_count": len(response.split()),
        "quotes_used": [],
        "beliefs_referenced": [],
        "stories_referenced": [],
    }
