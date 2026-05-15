"""Post-generation voice validation — catches posts that don't sound like the founder."""

from __future__ import annotations

import logging
from pathlib import Path

from ..utils.json_parser import parse_llm_json
from ..utils.text_utils import load_prompt, fill_prompt
from ..llm.base import LLMProvider
from .state import BatchState, AmplifiedPost

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).parent / "prompts"

VOICE_BLACKLIST = [
    "unveils", "ai-powered", "accessible communication",
    "the future of", "redefining", "excited to announce",
    "thrilled to share", "game-changing", "groundbreaking",
    "innovative solution", "cutting-edge", "revolutionizing",
    "leveraging", "synergy", "paradigm shift",
    "transformative", "best-in-class", "world-class",
    "disruptive", "seamless integration", "holistic approach",
]


def _deterministic_voice_check(text: str) -> list[str]:
    """Scan post text against VOICE_BLACKLIST. Returns list of matched phrases."""
    lower = text.lower()
    return [phrase for phrase in VOICE_BLACKLIST if phrase in lower]


def validate_voice(llm: LLMProvider, post: AmplifiedPost, state: BatchState) -> dict:
    """Run voice validation on a generated post. Returns scores + PASS/FAIL.

    First runs a deterministic keyword blacklist check (zero LLM cost).
    If that passes, runs the full LLM-based voice validation.
    """
    blacklist_hits = _deterministic_voice_check(post.text)
    if blacklist_hits:
        logger.info("[voice_validator] %s: blacklist FAIL — %s", post.label, ", ".join(blacklist_hits))
        return {
            "overall": "FAIL",
            "voice_marker_score": 0,
            "register_score": 0,
            "register_reads_as": "corporate",
            "violations": [f"Blacklisted phrase: '{p}'" for p in blacklist_hits],
            "suggestion": f"Remove corporate language: {', '.join(blacklist_hits)}",
            "blacklist_fail": True,
        }

    if getattr(state, "llm_router", None):
        llm = state.llm_router.for_task("voice_validation")
    template = load_prompt(PROMPTS_DIR / "voice_validation.txt")

    intern = state.founder_internalization
    argument_rhythm = intern.get("argument_rhythm", "Not documented")

    prompt = fill_prompt(
        template,
        post_text=post.text,
        calibration_paragraph=state.calibration_paragraph or "(no calibration paragraph available)",
        voice_markers="\n".join(f"- {m}" for m in state.voice_markers),
        argument_rhythm=str(argument_rhythm)[:1000],
        formatting_habits=str(state.formatting_habits),
        word_count_range=f"{state.word_count_range[0]}-{state.word_count_range[1]} words",
    )

    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=0.2, max_tokens=1000)
    _dur = int((_t.time() - _start) * 1000)
    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage=f"voice_validation_{post.label}",
            template="voice_validation.txt",
            prompt=prompt,
            response=response,
            temperature=0.2,
            max_tokens=1000,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
            metadata={"post_label": post.label},
        )

    if not isinstance(result, dict):
        return {"overall": "PASS", "voice_marker_score": 3, "register_score": 3}

    return result


def regenerate_with_voice_override(
    llm: LLMProvider,
    post: AmplifiedPost,
    validation: dict,
    state: BatchState,
) -> AmplifiedPost:
    """Regenerate a post that failed voice validation, with explicit voice-override."""
    if getattr(state, "llm_router", None):
        llm = state.llm_router.for_task("voice_regen")
    violations = validation.get("violations", [])
    suggestion = validation.get("suggestion", "")

    intern = state.founder_internalization
    argument_rhythm = intern.get("argument_rhythm", "")

    prompt = f"""The following post FAILED voice validation. Rewrite it keeping the same argument but fixing the voice violations.

## ORIGINAL POST (failed voice check)
{post.text}

## VOICE VIOLATIONS
{chr(10).join(f'- {v}' for v in violations) if violations else suggestion}

## WHAT TO FIX
The post must sound like THIS SPECIFIC FOUNDER, not like a corporate announcement, press release, or generic thought leader.

## FOUNDER VOICE MARKERS (these are the LAW)
{chr(10).join(f'- {m}' for m in state.voice_markers)}

## ARGUMENT RHYTHM
{str(argument_rhythm)[:500]}

## CALIBRATION PARAGRAPH (this is what the founder sounds like)
{state.calibration_paragraph}

## FORMATTING HABITS
{str(state.formatting_habits)}

## WORD COUNT RANGE
{state.word_count_range[0]}-{state.word_count_range[1]} words

## RULES
1. Keep the SAME core argument: {post.argument_compressed}
2. Replace the register — the founder card voice overrides the source register
3. Use AT LEAST 3 of the voice markers above
4. Match the argument rhythm pattern
5. The recognition test: would this founder read this and think "this is what I was going to say"?

## OUTPUT FORMAT
```json
{{{{
  "text": "the full rewritten post",
  "mode": "{post.mode}",
  "events_used": {post.events_used},
  "stories_used": [],
  "argument_compressed": "{post.argument_compressed}"
}}}}
```"""

    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=0.5, max_tokens=3000)
    _dur = int((_t.time() - _start) * 1000)
    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage=f"voice_regen_{post.label}",
            template="(inline voice-override prompt)",
            prompt=prompt,
            response=response,
            temperature=0.5,
            max_tokens=3000,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
            metadata={"post_label": post.label, "violations": violations},
        )

    v1_text = post.text
    v1_wc = post.word_count

    if isinstance(result, dict) and result.get("text"):
        post.text = result["text"]
        post.word_count = len(post.text.split())
        post.validation_result = {
            **validation,
            "regenerated": True,
            "v1_text": v1_text,
            "v1_word_count": v1_wc,
        }
        logger.info(
            "[voice_validator] Regenerated %s: v1=%d words → v2=%d words",
            post.label, v1_wc, post.word_count,
        )
    else:
        post.validation_result = {**validation, "regenerated": False, "v1_text": v1_text}
        logger.warning("[voice_validator] Regeneration failed for %s, keeping original", post.label)

    return post
