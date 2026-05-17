"""Post-generation voice validation — catches posts that don't sound like the founder."""

from __future__ import annotations

import logging
import re
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

    Pipeline:
      1. Python prechecks (zero LLM cost) — banned phrases, word count, marker rates, story usage
      2. Deterministic blacklist check (zero LLM cost)
      3. Full 5-dimension LLM validation via validate.txt
    """
    from .prechecks import run_all_prechecks

    precheck = run_all_prechecks(
        post.text, state,
        stories_declared=getattr(post, "stories_used", None) or [],
    )
    if not precheck["pass"]:
        logger.info("[voice_validator] %s: precheck FAIL — %s", post.label, precheck["failures"])
        return {
            "overall": "FAIL",
            "voice_marker_score": 0,
            "register_score": 0,
            "register_reads_as": "unknown",
            "violations": precheck["failures"],
            "suggestion": f"Fix: {'; '.join(precheck['failures'][:3])}",
            "precheck_fail": True,
        }

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
    template = load_prompt(PROMPTS_DIR / "validate.txt")

    intern = state.founder_internalization
    argument_rhythm = intern.get("argument_rhythm", "Not documented")
    marker_rates = getattr(state, "marker_rates", {})

    prompt = fill_prompt(
        template,
        post_text=post.text,
        calibration_paragraph=state.calibration_paragraph or "(no calibration paragraph available)",
        voice_markers="\n".join(f"- {m}" for m in state.voice_markers),
        argument_rhythm=str(argument_rhythm)[:1000],
        formatting_habits=str(state.formatting_habits),
        marker_rates=str(marker_rates) if marker_rates else "Not computed",
    )

    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=0.2, max_tokens=1000)
    _dur = int((_t.time() - _start) * 1000)
    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage=f"voice_validation_{post.label}",
            template="validate.txt",
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


# ---------------------------------------------------------------------------
# Quality-gate helpers (Fixes 4, 5, 6) — pure-Python checks, zero LLM cost.
# ---------------------------------------------------------------------------

_T1_NUM = re.compile(
    r"\b\d+[\.\)]\s|\$[\d,]+(?:\.\d+)?[KMB]?\b|\b\d+%\b|\b\d+x\b|"
    r"\bNot one\.\s+Not two\.|\bonce\.\s+twice\.|\bthree\b.{0,15}\bbuyers\b",
    re.I,
)
_T1_ROLE = re.compile(
    r"\b(CRO|CEO|CTO|CFO|CMO|COO|VP|head of [\w ]+|director|founder|engineer|"
    r"product manager|PM|AE|SE|SDR|sales rep|customer success|CS team|investor)\b",
    re.I,
)
_T2_QUOTE = re.compile(r'["""“”][^"""“”]{20,200}["""“”]')
_T2_TIME = re.compile(
    r"\b(last (?:week|month|quarter|year)|\d+ (?:weeks?|months?|years?|"
    r"minutes?|hours?|days?) (?:ago|later)|month two|six weeks|thirty minutes|"
    r"yesterday|tomorrow|two years ago)\b",
    re.I,
)
_TIME_MEASURE = re.compile(
    r"\b\d+\s*(?:weeks?|months?|years?|minutes?|hours?|days?|quarters?)\b",
    re.I,
)
_ABSTRACT_WORDS = {
    "system", "function", "structure", "framework", "model", "approach",
    "mechanism", "paradigm", "fundamental", "essential", "crucial", "valuable",
    "meaningful", "powerful",
}


def check_anchor_specificity(post: AmplifiedPost) -> dict:
    """Detect whether the post body contains a Tier 1 or Tier 2 anchor.

    Tier 1 — specific operating rule: numbered emphasis AND a named role.
    Tier 2 — named scene with quoted dialogue AND specific time marker.

    Generic third-degree patterns ("I've watched war rooms at $500M companies")
    fail both tiers — they're plausible but not anchored.
    """
    text = post.text or ""
    has_num = bool(_T1_NUM.search(text))
    has_role = bool(_T1_ROLE.search(text))
    has_quote = bool(_T2_QUOTE.search(text))
    has_time = bool(_T2_TIME.search(text))

    if has_num and has_role:
        return {"pass": True, "tier": 1, "reason": "tier1_operating_rule"}
    if has_quote and has_time:
        return {"pass": True, "tier": 2, "reason": "tier2_named_scene"}
    return {
        "pass": False,
        "tier": None,
        "reason": (
            f"no_tier1_or_tier2 (num={has_num},role={has_role},"
            f"quote={has_quote},time={has_time})"
        ),
    }


def check_closer_shape(post: AmplifiedPost) -> dict:
    """Evaluate whether the closing 1-2 sentences are compressed + concrete.

    Pass requires >=2 of:
      - Specific time measurement ("six weeks", "thirty minutes")
      - Parallel structure with twist on the second clause
      - Compression (closer <= 30 words)
      - Concrete imagery (low abstract-word ratio)
    """
    text = (post.text or "").strip()
    if not text:
        return {"pass": False, "score": 0, "wc": 0, "reason": "empty_text"}

    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s for s in sentences if s.strip()]
    closer = " ".join(sentences[-2:]) if len(sentences) >= 2 else sentences[-1]
    closer_words = closer.split()
    wc = len(closer_words)

    has_time = bool(_TIME_MEASURE.search(closer))

    has_parallel_twist = False
    if len(sentences) >= 2:
        s_minus_2 = sentences[-2].split()
        s_minus_1 = sentences[-1].split()
        if len(s_minus_2) >= 2 and len(s_minus_1) >= 2:
            has_parallel_twist = (
                s_minus_2[0].lower() == s_minus_1[0].lower()
                and s_minus_2[1].lower() == s_minus_1[1].lower()
            )

    is_short = wc <= 30

    if wc > 0:
        abstract_count = sum(1 for w in closer_words if w.lower().strip(".,!?;:") in _ABSTRACT_WORDS)
        abstract_ratio = abstract_count / wc
    else:
        abstract_ratio = 0.0
    is_concrete = abstract_ratio < 0.05

    score = int(has_time) + int(has_parallel_twist) + int(is_short) + int(is_concrete)
    return {
        "pass": score >= 2,
        "score": score,
        "wc": wc,
        "reason": (
            f"time={has_time},parallel={has_parallel_twist},"
            f"short={is_short},concrete={is_concrete}"
        ),
    }


def run_voice_validation_with_retries(
    llm: LLMProvider,
    post: AmplifiedPost,
    state: BatchState,
    max_passes: int = 2,
) -> AmplifiedPost:
    """Validate voice; if FAIL, regen up to max_passes times. Stamp threshold
    violation flag in quality_flags if still failing after max attempts.
    Increments post.regen_count for each regen attempt.
    """
    for _ in range(max_passes):
        validation = validate_voice(llm, post, state)
        post.validation_result = validation
        if validation.get("overall") != "FAIL":
            post.voice_score = min(
                validation.get("voice_marker_score", 3),
                validation.get("register_score", 3),
            )
            return post
        post = regenerate_with_voice_override(llm, post, validation, state)
        post.regen_count += 1

    final = validate_voice(llm, post, state)
    post.validation_result = final
    if final.get("overall") == "FAIL":
        post.quality_flags["voice_threshold_warning"] = True
        post.quality_flags["voice_violations_final"] = final.get("violations", [])
        logger.warning(
            "[voice_validator] %s: shipped with voice threshold violation after %d regens",
            post.label, max_passes,
        )
    post.voice_score = min(
        final.get("voice_marker_score", 3),
        final.get("register_score", 3),
    )
    return post
