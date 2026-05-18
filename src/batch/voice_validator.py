"""Post-generation voice validation — catches posts that don't sound like the founder."""

from __future__ import annotations

import json
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
    """v5 shim: per-post validation moved into pack-level validate_pack()
    (05_validate.txt). Old callers get a PASS so they don't trigger regen.

    Python prechecks + blacklist check still run as zero-cost gates.
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

    # No per-post LLM call in v5; the heavy validation runs once at pack level.
    return {"overall": "PASS", "voice_marker_score": 3, "register_score": 3}


def _normalize_sentence(s: str) -> str:
    """Lowercase + strip punctuation/whitespace for cross-variant comparison."""
    s = s.lower().strip()
    # Remove common trailing punctuation and condense whitespace.
    return re.sub(r"\s+", " ", re.sub(r"[\.\?\!\,\;\:\"\'\(\)]+", "", s))


def _sentence_token_set(s: str) -> set[str]:
    return set(_normalize_sentence(s).split())


def _body_diff_check(a_posts: list[AmplifiedPost], jaccard_threshold: float = 0.85) -> dict:
    """Compare each pair of Batch A posts for sentence-level body overlap.

    The opener (first 2 sentences) is allowed to mirror by design — we only
    compare BODY sentences. Two sentences count as "shared" when their token
    set Jaccard similarity >= threshold (default 0.85).

    Status:
      0-2 shared per pair → acceptable
      3-5 shared          → warning
      6+ shared           → fail; later post in the pair flagged for regen
    """
    if len(a_posts) < 2:
        return {"passed": True, "pair_results": [], "regen_targets": []}

    def _body_sentences(post: AmplifiedPost) -> list[str]:
        text = (post.text or "").strip()
        if not text:
            return []
        # Split on sentence terminators; drop the first 2 (opener mirror band).
        sentences = re.split(r"(?<=[\.\!\?])\s+", text)
        return [s.strip() for s in sentences[2:] if len(s.strip()) >= 10]

    sentences_by_post = {p.label: _body_sentences(p) for p in a_posts}

    pair_results = []
    regen_targets: list[str] = []
    for i, p1 in enumerate(a_posts):
        for p2 in a_posts[i + 1:]:
            s1_list = sentences_by_post[p1.label]
            s2_list = sentences_by_post[p2.label]
            shared = 0
            for a in s1_list:
                a_tokens = _sentence_token_set(a)
                if not a_tokens:
                    continue
                for b in s2_list:
                    b_tokens = _sentence_token_set(b)
                    if not b_tokens:
                        continue
                    union = a_tokens | b_tokens
                    inter = a_tokens & b_tokens
                    if union and (len(inter) / len(union)) >= jaccard_threshold:
                        shared += 1
                        break  # don't double-count the same sentence in p1
            if shared >= 6:
                status = "fail"
                regen_targets.append(p2.label)
            elif shared >= 3:
                status = "warn"
            else:
                status = "acceptable"
            pair_results.append({
                "pair": f"{p1.label}/{p2.label}",
                "shared_sentences": shared,
                "status": status,
            })

    return {
        "passed": not regen_targets,
        "pair_results": pair_results,
        "regen_targets": regen_targets,
    }


def validate_pack(
    llm: LLMProvider,
    pack_posts: list[AmplifiedPost],
    state: BatchState,
) -> dict:
    """v6: One LLM call validates the pack via 05_validate.txt.

    The v6 validator now consumes:
    - `anchor_inventory` (full master list, for TIER ladder verification)
    - `pack_history` (30-day rolling, for cross-pack saturation)

    Outputs `per_post_validation[].scores` (10 params), `pack_level_checks`,
    `pack_decision.ship_or_regen_or_reject`, `regen_targets[]` with
    `explicit_regen_instructions`.

    Also fixes Bug A: writes validator scores back to each post keyed by
    label (not the broken global assignment from v5.1).
    """
    if getattr(state, "llm_router", None):
        try:
            llm = state.llm_router.for_task("validate")
        except Exception:
            llm = state.llm_router.for_task("voice_validation")

    template = load_prompt(PROMPTS_DIR / "validate.txt")

    voice = state.voice_load or state.founder_internalization or {}

    # v6 posts JSON includes pre_commit + self_scores so the validator can
    # cross-check the generator's self-assessment against its own scoring.
    posts_arr = []
    for p in pack_posts:
        posts_arr.append({
            "label": p.label,
            "batch": p.batch,
            "text": p.text,
            "argument_compressed": p.argument_compressed,
            "mechanic": p.mechanic,
            "entry_door": p.entry_door,
            "closer_mechanic": p.closer_mechanic,
            "word_count": p.word_count,
            "pre_commit": p.pre_commit or {},
            "self_scores": p.self_scores or {},
            "anchor_consumed_id": p.anchor_consumed_id,
            "voice_markers_used": (p.pre_commit or {}).get("_voice_markers_used_runtime", []),
        })
    posts_json = json.dumps(posts_arr, ensure_ascii=False)

    inv_full = state.anchor_inventory or {}
    inv_list = inv_full.get("anchor_inventory", []) or []
    pack_history = state.pack_history or []

    # The active dissection is the latest one (last source processed).
    dissection_for_pack = (state.source_dissections[-1] if state.source_dissections else {})

    prompt = fill_prompt(
        template,
        posts=posts_json,
        voice_load=json.dumps(voice, ensure_ascii=False)[:6000],
        calibration_paragraph=voice.get("calibration_paragraph") or state.calibration_paragraph or "(no calibration paragraph available)",
        voice_markers="\n".join(f"- {m}" for m in state.voice_markers),
        argument_rhythm=str(voice.get("argument_rhythm", "Not documented"))[:1000],
        formatting_habits=str(state.formatting_habits),
        founder_first_name=state.founder_first_name or state.founder_slug.title(),
        anchor_inventory=json.dumps(inv_list, ensure_ascii=False)[:8000] or "(no inventory)",
        pack_history=json.dumps(pack_history, ensure_ascii=False)[:3000] or "(no recent packs)",
        dissection=json.dumps(dissection_for_pack, ensure_ascii=False)[:4000] or "{}",
    )

    import time as _t
    _start = _t.time()
    try:
        response = llm.generate(prompt, temperature=0.2, max_tokens=6000)
    except Exception as e:
        logger.warning("[validate_pack] API error: %s — defaulting to SHIP", e)
        return {"pack_decision": {"ship_or_regen_or_reject": "ship", "quality_floor_met": True, "regen_targets": []}}
    _dur = int((_t.time() - _start) * 1000)
    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage="validate_pack",
            template="05_validate.txt",
            prompt=prompt,
            response=response,
            temperature=0.2,
            max_tokens=6000,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
            llm=llm,
            metadata={"posts_count": len(pack_posts)},
        )

    if not isinstance(result, dict):
        logger.warning("[validate_pack] parse failed — defaulting to SHIP (warn)")
        return {"pack_decision": {"ship_or_regen_or_reject": "ship", "quality_floor_met": True, "regen_targets": []}}

    # Bug A fix: per-post keyed lookup, not a flat overwrite.
    # Also extended for v6.1 sub-mechanic fields + Parameter 1 hard veto log.
    per_post = result.get("per_post_validation", []) or []
    by_label: dict = {entry.get("label"): entry for entry in per_post if isinstance(entry, dict)}
    for post in pack_posts:
        entry = by_label.get(post.label) or {}
        post.validator_scores = entry.get("scores", {}) or {}
        post.passes_9_7_floor = bool(entry.get("passes_9_7_floor", False))
        # v6.1 sub-mechanic tracking
        post.actual_sub_mechanic_used = str(entry.get("actual_sub_mechanic_used", "") or "")
        post.required_sub_mechanic = str(entry.get("required_sub_mechanic", "") or "")
        post.sub_mechanic_match = bool(entry.get("sub_mechanic_match", False))
        post.parameter_1_hard_veto_triggered = bool(entry.get("parameter_1_hard_veto_triggered", False))
        # Keep the full per-post record for downstream consumers; preserves
        # legacy validation_result API too.
        post.validation_result = entry

        # v6.1: log Parameter 1 hard veto distinctly when it fires on a Batch A
        # post. README §"What v6.1 will produce" depends on this being visible
        # so the user can diagnose mirror collapse from stderr.
        if post.batch == "A" and post.parameter_1_hard_veto_triggered:
            logger.warning(
                "[validate_pack] %s: Parameter 1 HARD VETO — sub-mechanic mismatch "
                "(required=%r, actual=%r)",
                post.label, post.required_sub_mechanic, post.actual_sub_mechanic_used,
            )

    decision = result.get("pack_decision", {}) or {}
    logger.info(
        "[validate_pack] decision=%s quality_floor_met=%s regen_targets=%s",
        decision.get("ship_or_regen_or_reject", "?"),
        decision.get("quality_floor_met", "?"),
        [t.get("label") for t in decision.get("regen_targets", []) if isinstance(t, dict)],
    )

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
            llm=llm,
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
