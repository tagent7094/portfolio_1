"""5-gate Opening Line Amplifier — diagnose, generate alternatives, test convergence."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..utils.json_parser import parse_llm_json
from ..utils.text_utils import load_prompt, fill_prompt
from ..llm.base import LLMProvider
from ..utils.slop_detection import is_slop as _is_slop, AI_SLOP_PATTERNS
from .state import BatchState, AmplifiedPost

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).parent / "prompts"
TEMPLATE_REPO_PATH = Path(__file__).parent / "template_repository.json"


def _load_template_repository() -> list[dict]:
    """Load the 13-template repository from JSON."""
    if TEMPLATE_REPO_PATH.exists():
        with open(TEMPLATE_REPO_PATH) as f:
            return json.load(f)
    return []


TEMPLATE_REPOSITORY = _load_template_repository()
VALID_MECHANICS = {t["id"] for t in TEMPLATE_REPOSITORY} if TEMPLATE_REPOSITORY else {
    "specific_number", "juxtaposition", "confession", "quote_hook",
    "scene_entry", "decision_reveal", "contrarian", "pattern_observation",
}

_MECHANIC_ALIASES = {
    "first-person confession": "confession",
    "first person confession": "confession",
    "contrarian declaration": "contrarian",
    "contrarian claim": "contrarian",
    "quote hook": "quote_hook",
    "quote_hook + reaction": "quote_hook",
    "quote hook + reaction": "quote_hook",
    "scene entry": "scene_entry",
    "scene-entry": "scene_entry",
    "decision reveal": "decision_reveal",
    "decision-reveal": "decision_reveal",
    "specific number": "specific_number",
    "specific_number + context": "specific_number",
    "specific number + context": "specific_number",
    "pattern observation": "pattern_observation",
    "pattern-observation": "pattern_observation",
    "tension pair": "tension_pair",
    "tension-pair": "tension_pair",
    "before/after": "before_after",
    "before after": "before_after",
    "before-after": "before_after",
    "before/after snapshot": "before_after",
    "micro story": "micro_story",
    "micro-story": "micro_story",
    "authority redirect": "authority_redirect",
    "authority-redirect": "authority_redirect",
    "data inversion": "data_inversion",
    "data-inversion": "data_inversion",
}


_DOOR_FAMILIES = {
    "scene_drop": {"scene_entry", "scene_drop", "micro_story"},
    "diagnostic_question": {"diagnostic_question"},
    "borrowed_authority_quote": {"quote_hook", "authority_redirect"},
    "data_contradiction": {"data_inversion", "juxtaposition"},
    "confession": {"confession"},
    "physical_object": {"scene_entry", "physical_object"},
    "direct_address": {"direct_address"},
    "mocked_counter_example": {"contrarian", "pattern_observation"},
    "contrarian_claim": {"contrarian", "contrarian_claim"},
    "parallel_structure": {"juxtaposition", "tension_pair"},
    "age_time_anchor": {"specific_number", "scene_entry"},
    "second_party_verdict": {"quote_hook", "authority_redirect"},
}


def _normalize_mechanic(raw: str) -> str:
    """Map free-text mechanic names to canonical VALID_MECHANICS identifiers."""
    if not raw:
        return "unknown"
    lower = raw.lower().strip()
    if lower in VALID_MECHANICS:
        return lower
    if lower in _MECHANIC_ALIASES:
        return _MECHANIC_ALIASES[lower]
    for canon in VALID_MECHANICS:
        if canon in lower or lower in canon:
            return canon
    return raw


def _mechanic_matches_door(current_mechanic: str, assigned_door: str) -> bool:
    """Check if the opener's identified mechanic matches its assigned entry door."""
    if not current_mechanic or not assigned_door:
        return False
    mech = _normalize_mechanic(current_mechanic)
    door = assigned_door.lower().strip()
    if mech == door:
        return True
    family = _DOOR_FAMILIES.get(door, set())
    return mech in family


def _count_mechanic_in_peers(peers: list, mechanic: str) -> int:
    """Count how many already-processed posts use this mechanic."""
    if not mechanic:
        return 0
    normalized = _normalize_mechanic(mechanic)
    return sum(1 for p in peers if _normalize_mechanic(p.mechanic) == normalized)


def _should_apply_batch_a_variant(post: AmplifiedPost, best: dict | None) -> tuple[bool, str]:
    """Batch A ALWAYS preserves the source-mirrored opener.

    User rule: "no creativity in A batch strictly". The source mirror is
    Batch A's defining property — all 3 A posts share the source's opener
    mechanic family (audience-address + scale credential + count promise,
    etc.). Applying body-derived variants (buried gold lines) breaks that
    mirror — A1/A2/A3 end up with different mechanics instead of the
    common source-mirror structure.

    Variants are still computed and surfaced as `recommended_variant` for
    operator inspection, but never applied to the shipped post. If the
    opener fails critical gates, regenerate via transpose with a
    mirror-fix hint — do NOT swap in body content.
    """
    return False, "batch_a_preserve_mirror_unconditional"


def _should_preserve_door(
    post: AmplifiedPost,
    diag: dict,
    best: dict | None,
    peers: list | None,
) -> tuple[bool, str]:
    """Unified door-preservation logic (Batch B only — A short-circuits earlier).

    Returns (should_preserve, reason). Tightened in 2026-05 to require:
      - validation_result.overall == "PASS" strictly (no voice_score fallback)
      - voice_fit, coherence, mode_preservation gates all pass (source_mirror also for A)
      - mechanic_matches_door AND no saturation
    """
    vr = getattr(post, "validation_result", {}) or {}
    voice_strict_pass = vr.get("overall") == "PASS"

    gates = post.gates or {}
    required = ["voice_fit", "coherence", "mode_preservation"]
    if post.batch == "A":
        required.append("source_mirror")
    gates_ok = all(gates.get(g, False) for g in required)

    current_mech = diag.get("current_mechanic", "")
    door_matches = _mechanic_matches_door(current_mech, post.entry_door)

    best_mech = (best or {}).get("mechanic", "") if best else ""
    would_saturate = (
        peers is not None
        and best_mech
        and _count_mechanic_in_peers(peers, best_mech) >= 3
    )

    if voice_strict_pass and gates_ok and door_matches and not would_saturate:
        return True, "strict_pass"
    if would_saturate and gates_ok:
        return True, "saturation_blocked"
    return False, (
        f"guard_failed(voice_pass={voice_strict_pass},gates_ok={gates_ok},"
        f"door_match={door_matches},sat={would_saturate})"
    )


def _apply_best_opener(post: AmplifiedPost, best: dict) -> AmplifiedPost:
    """Replace the post's opening paragraph with the best alternative.

    v6.1: NO Python paragraph dedup. Per "deterministic API calls only"
    directive — the pack-level validator catches duplicate paragraphs via
    its `duplicate_paragraph_within_post` check. Previous Phase 2.6
    Jaccard-0.6 dedup could drop legitimate echo structure.
    """
    paragraphs = post.text.strip().split("\n\n")
    if not paragraphs:
        return post

    post.original_opening = paragraphs[0]
    paragraphs[0] = best["opening"]
    post.text = "\n\n".join(paragraphs)
    post.final_opening = best["opening"]
    post.mechanic = _normalize_mechanic(best.get("mechanic", ""))
    post.rating = best.get("rating", 0)
    post.word_count = len(post.text.split())
    return post




def amplify_post_v2(
    llm: LLMProvider,
    post: AmplifiedPost,
    state: BatchState,
    source_dissection: dict | None = None,
    peers: list | None = None,
) -> AmplifiedPost:
    """v5: Opening-line amplifier — Batch B ONLY.

    Uses 04_amplify.txt. The new prompt drops `source_dissection` because v5
    keeps Batch A's mirror discipline upstream (in 03_generate.txt). Batch A
    posts pass through unchanged.
    """
    # Per v5 contract: never amplify Batch A. Caller should already be
    # filtering, but enforce defensively here too.
    if post.batch == "A":
        post.original_opening = post.text.strip().split("\n\n")[0] if post.text else ""
        post.final_opening = post.original_opening
        post.mechanic = post.mechanic or "mirrored"
        post.rating = 0
        return post

    if getattr(state, "llm_router", None):
        llm = state.llm_router.for_task("amplify")

    logger.info("[amplifier_v2] Processing %s...", post.label)

    template = load_prompt(PROMPTS_DIR / "amplify.txt")

    prompt = fill_prompt(
        template,
        post_text=post.text,
        post_label=post.label,
        voice_markers="\n".join(f"- {m}" for m in state.voice_markers),
        mode=post.mode or "declaring",
    )

    import time as _t
    _start = _t.time()
    try:
        response = llm.generate(prompt, temperature=0.3, max_tokens=4000, thinking_budget=0)
    except Exception as e:
        logger.warning("[amplifier_v2] %s: API error (%s), keeping original", post.label, e)
        post.original_opening = post.text.strip().split("\n\n")[0] if post.text else ""
        post.final_opening = post.original_opening
        post.mechanic = "kept"
        post.rating = 5
        return post
    _dur = int((_t.time() - _start) * 1000)

    if not response or not response.strip():
        logger.warning("[amplifier_v2] %s: empty response, keeping original", post.label)
        post.original_opening = post.text.strip().split("\n\n")[0] if post.text else ""
        post.final_opening = post.original_opening
        post.mechanic = "kept"
        post.rating = 5
        return post

    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage=f"amplify_v2_{post.label}",
            template="04_amplify.txt",
            prompt=prompt,
            response=response,
            temperature=0.3,
            max_tokens=4000,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
            llm=llm,
            metadata={"label": post.label, "batch": post.batch},
        )

    if not isinstance(result, dict):
        logger.warning("[amplifier_v2] %s: parse failed, keeping original", post.label)
        post.original_opening = post.text.strip().split("\n\n")[0] if post.text else ""
        post.final_opening = post.original_opening
        post.mechanic = "kept"
        post.rating = 5
        return post

    # Extract diagnosis
    diag = result.get("diagnosis", {})
    post.original_opening = post.text.strip().split("\n\n")[0] if post.text else ""
    gates = diag.get("gates", {})
    post.gates = {k: v.get("pass", True) if isinstance(v, dict) else v for k, v in gates.items()}
    post.buried_gold = diag.get("buried_gold", "")
    post.weakness = diag.get("weakness", "")

    all_pass = diag.get("all_gates_pass", True)
    gate7_fail_reason = ""
    if source_dissection and post.batch == "A":
        gate7 = gates.get("source_mirror", {})
        if isinstance(gate7, dict) and not gate7.get("pass", True):
            all_pass = False
            failed_sub = []
            if not gate7.get("mechanic_match", True):
                failed_sub.append("mechanic")
            if not gate7.get("body_format_match", True):
                failed_sub.append(f"body_format(actual={gate7.get('body_format_actual', '?')})")
            if not gate7.get("closer_mechanic_match", True):
                failed_sub.append(f"closer(actual={gate7.get('closer_mechanic_actual', '?')})")
            gate7_fail_reason = ",".join(failed_sub) or "unspecified"
            logger.info("[amplifier_v2] %s: Gate 7 FAIL — %s", post.label, gate7_fail_reason)

    is_slop = _is_slop(post.original_opening)

    # Extract variants
    alternatives = []
    for v in result.get("variants", []):
        if not isinstance(v, dict) or "opening" not in v:
            continue
        if _is_slop(v["opening"]):
            continue
        v["mechanic"] = _normalize_mechanic(v.get("mechanic", ""))
        alternatives.append(v)

    post.versions_considered = len(alternatives)
    post.opener_variants = alternatives

    # Batch A: preserve mirror by default; apply variant only when critical
    # gates fail AND a viable variant exists (variants are drawn from body
    # buried gold, so this reorganizes existing content — no new creativity).
    if post.batch == "A":
        best_a = None
        if alternatives:
            best_a = max(alternatives, key=lambda v: (
                1 if v.get("coherence_with_body", True) else 0,
                1 if v.get("plausibility", True) else 0,
                v.get("rating", 0),
            ))
            post.recommended_variant = best_a.get("variant", "A")

        should_apply, apply_reason = _should_apply_batch_a_variant(post, best_a)
        if should_apply:
            post = _apply_best_opener(post, best_a)
            post.mechanic = "mirrored"  # keep slot label; A is still A
            post.actual_mechanic = _normalize_mechanic(best_a.get("mechanic", ""))
            post.rating = best_a.get("rating", 0)
            logger.info(
                "[amplifier_v2] %s: Batch A variant APPLIED (reason=%s, actual_mechanic=%s)",
                post.label, apply_reason, post.actual_mechanic,
            )
            replaced = True
        else:
            post.final_opening = post.original_opening
            post.mechanic = "mirrored"
            post.actual_mechanic = _normalize_mechanic(diag.get("current_mechanic", ""))
            post.rating = 0
            replaced = False

        state.amplifier_log.append({
            "label": post.label,
            "original": post.original_opening[:100],
            "final": post.final_opening[:100],
            "gates_passed": all(post.gates.values()) if post.gates else True,
            "replaced": replaced,
            "variants_count": len(alternatives),
            "recommended": getattr(post, "recommended_variant", ""),
            "v2": True,
            "batch_a_apply_reason": apply_reason if not replaced else None,
            "batch_a_applied": replaced,
        })
        return post

    if alternatives:
        def _sort_key(v):
            coh = 1 if v.get("coherence_with_body", True) else 0
            plaus = 1 if v.get("plausibility", True) else 0
            vfit = 1 if v.get("voice_fit", True) else 0
            mode_fit = 1 if v.get("mode_preservation", True) else 0
            rating = v.get("rating", 0)
            return (coh, plaus, vfit, mode_fit, rating)

        best = max(alternatives, key=_sort_key)
        post.recommended_variant = best.get("variant", "A")
        best_rating = best.get("rating", 0)

        BASELINE_RATING = 7
        rating_lift = best_rating >= BASELINE_RATING + 1
        coh_ok = best.get("coherence_with_body", True)
        plaus_ok = best.get("plausibility", True)
        vfit_ok = best.get("voice_fit", True)
        mode_ok = best.get("mode_preservation", True)
        variant_safe = coh_ok and plaus_ok and vfit_ok and mode_ok

        door_preserved, preserve_reason = _should_preserve_door(post, diag, best, peers)
        if door_preserved:
            logger.info(
                "[amplifier_v2] %s: door-preserved (reason=%s, entry_door=%s, "
                "best_variant_rating=%d)",
                post.label, preserve_reason, post.entry_door, best_rating,
            )

        if not door_preserved and ((not all_pass) or is_slop or (rating_lift and variant_safe)):
            apply_reason = (
                f"gate_fail({gate7_fail_reason})" if not all_pass and gate7_fail_reason
                else "gate_fail" if not all_pass
                else "slop" if is_slop
                else f"rating_lift({best_rating})"
            )
            post = _apply_best_opener(post, best)
            post.actual_mechanic = post.mechanic  # replaced opener — actual matches mechanic
            logger.info("[amplifier_v2] %s: replaced opener (mechanic=%s, rating=%d, reason=%s)",
                        post.label, post.mechanic, post.rating, apply_reason)
        else:
            post.final_opening = post.original_opening
            post.mechanic = _normalize_mechanic(diag.get("current_mechanic", "kept"))
            post.actual_mechanic = post.mechanic
            post.rating = 5
    else:
        post.final_opening = post.original_opening
        post.mechanic = _normalize_mechanic(diag.get("current_mechanic", "unchanged" if not all_pass else "kept"))
        post.actual_mechanic = post.mechanic
        post.rating = 5 if all_pass else 0

    state.amplifier_log.append({
        "label": post.label,
        "original": post.original_opening[:100],
        "final": post.final_opening[:100],
        "gates_passed": all(post.gates.values()) if post.gates else True,
        "replaced": post.original_opening != post.final_opening,
        "variants_count": len(alternatives),
        "recommended": post.recommended_variant,
        "v2": True,
    })

    return post




def amplify_batch_v2(
    llm: LLMProvider,
    posts: list[AmplifiedPost],
    state: BatchState,
    source_dissection: dict | None = None,
    never_replace: bool = False,
) -> list[AmplifiedPost]:
    """v5 shim: amplify_batch.txt is gone (merged into 04_amplify.txt which
    runs per-post, B-only). When called with Batch A (`never_replace=True`),
    return posts unchanged — Batch A never amplifies in v5.
    When called with Batch B posts, delegate to per-post amplify_post_v2.
    """
    if not posts:
        return posts

    if never_replace:
        # Batch A path: no amplification in v5.
        for p in posts:
            if not p.original_opening and p.text:
                p.original_opening = p.text.split("\n\n")[0]
            p.final_opening = p.original_opening
            p.mechanic = p.mechanic or "mirrored"
            p.rating = 0
        return posts

    # Batch B path: per-post amplify with the v5 prompt.
    results: list[AmplifiedPost] = []
    for p in posts:
        results.append(amplify_post_v2(llm, p, state, source_dissection=None, peers=results))
    return results


def _unused_legacy_amplify_batch_v2(
    llm: LLMProvider,
    posts: list[AmplifiedPost],
    state: BatchState,
    source_dissection: dict | None = None,
    never_replace: bool = False,
) -> list[AmplifiedPost]:
    """v4 implementation kept inert — references amplify_batch.txt which no
    longer exists in v5. The active function above replaces it."""
    if getattr(state, "llm_router", None):
        llm = state.llm_router.for_task("amplify")

    if not posts:
        return posts

    if len(posts) > 8:
        mid = len(posts) // 2
        left = amplify_batch_v2(llm, posts[:mid], state, source_dissection=source_dissection, never_replace=never_replace)
        right = amplify_batch_v2(llm, posts[mid:], state, source_dissection=source_dissection, never_replace=never_replace)
        return left + right

    template = load_prompt(PROMPTS_DIR / "amplify_batch.txt")

    posts_block_parts = []
    for post in posts:
        posts_block_parts.append(
            f"### POST: {post.label}\nMode: {post.mode}\n\n{post.text}\n\n---"
        )
    posts_block = "\n\n".join(posts_block_parts)

    source_dissection_note = ""
    if source_dissection and never_replace:
        import json as _json
        source_dissection_note = (
            f"\n\n## SOURCE DISSECTION (for Gate 7 — Batch A mirror fidelity)\n"
            f"{_json.dumps(source_dissection, ensure_ascii=False)[:2000]}"
        )

    prompt = fill_prompt(
        template,
        voice_markers="\n".join(f"- {m}" for m in state.voice_markers),
        posts_block=posts_block + source_dissection_note,
        post_count=str(len(posts)),
    )

    max_tokens = min(len(posts) * 2500, 30000)
    batch_type = "A" if never_replace else "B"

    logger.info("[amplifier_batch] Processing %d %s posts in single call (max_tokens=%d)...",
                len(posts), batch_type, max_tokens)

    import time as _t
    _start = _t.time()
    try:
        response = llm.generate(prompt, temperature=0.3, max_tokens=max_tokens, thinking_budget=0)
    except Exception as e:
        logger.warning("[amplifier_batch] API error (%s), falling back to sequential", e)
        return _fallback_sequential(llm, posts, state)
    _dur = int((_t.time() - _start) * 1000)

    if not response or not response.strip():
        logger.warning("[amplifier_batch] empty response, falling back to sequential")
        return _fallback_sequential(llm, posts, state)

    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage=f"amplify_batch_{batch_type}",
            template="amplify_batch.txt",
            prompt=prompt,
            response=response,
            temperature=0.3,
            max_tokens=max_tokens,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
            llm=llm,
            metadata={"post_count": len(posts), "never_replace": never_replace},
        )

    if not isinstance(result, dict) or "posts" not in result:
        logger.warning("[amplifier_batch] parse failed, falling back to sequential")
        return _fallback_sequential(llm, posts, state)

    posts_result = result["posts"]
    amplified = []
    failed_labels = []

    for post in posts:
        post_data = posts_result.get(post.label)
        if not post_data or not isinstance(post_data, dict):
            failed_labels.append(post.label)
            amplified.append(post)
            continue
        post = _apply_batch_result(post, post_data, state, peers=amplified, never_replace=never_replace)
        amplified.append(post)

    if failed_labels:
        logger.warning("[amplifier_batch] %d posts failed parse, running sequential: %s",
                       len(failed_labels), failed_labels)
        for i, post in enumerate(amplified):
            if post.label in failed_labels:
                amplified[i] = amplify_post_v2(llm, post, state, source_dissection=source_dissection, peers=amplified)

    from collections import Counter
    preserved = sum(1 for p in amplified if p.original_opening == p.final_opening and p.mechanic not in ("unchanged", "unknown"))
    replaced = sum(1 for p in amplified if p.original_opening != p.final_opening)
    distribution = Counter(p.mechanic for p in amplified if p.mechanic)
    logger.info(
        "[amplifier_pack_summary] preserved=%d/%d replaced=%d distribution=%s",
        preserved, len(amplified), replaced, dict(distribution),
    )

    logger.info("[amplifier_batch] Completed %d %s posts in %.1fs", len(posts), batch_type, _dur / 1000)
    return amplified


def _fallback_sequential(llm, posts, state):
    """Fall back to per-post amplification."""
    logger.info("[amplifier_batch] Falling back to sequential (%d posts)", len(posts))
    results = []
    for p in posts:
        results.append(amplify_post_v2(llm, p, state, source_dissection=None, peers=results))
    return results


def _apply_batch_result(post: AmplifiedPost, data: dict, state: BatchState, peers: list | None = None, never_replace: bool = False) -> AmplifiedPost:
    """Apply batch amplifier result to a single post."""
    diag = data.get("diagnosis", {})
    post.original_opening = post.text.strip().split("\n\n")[0] if post.text else ""

    gates = diag.get("gates", {})
    post.gates = {k: v.get("pass", True) if isinstance(v, dict) else v for k, v in gates.items()}
    post.buried_gold = diag.get("buried_gold", "")
    post.weakness = diag.get("weakness", "")

    all_pass = diag.get("all_gates_pass", True)
    is_slop = _is_slop(post.original_opening)

    alternatives = []
    for v in data.get("variants", []):
        if not isinstance(v, dict) or "opening" not in v:
            continue
        if _is_slop(v["opening"]):
            continue
        v["mechanic"] = _normalize_mechanic(v.get("mechanic", ""))
        alternatives.append(v)

    post.versions_considered = len(alternatives)
    post.opener_variants = alternatives

    if alternatives:
        def _sort_key(v):
            coh = 1 if v.get("coherence_with_body", True) else 0
            plaus = 1 if v.get("plausibility", True) else 0
            vfit = 1 if v.get("voice_fit", True) else 0
            mode_fit = 1 if v.get("mode_preservation", True) else 0
            rating = v.get("rating", 0)
            return (coh, plaus, vfit, mode_fit, rating)

        best = max(alternatives, key=_sort_key)
        post.recommended_variant = best.get("variant", "A")

    # Batch A: preserve mirror by default; apply variant when critical gates
    # fail AND a viable variant exists. never_replace=True still forces
    # preservation (used by callers that need it unconditionally).
    if never_replace or post.batch == "A":
        best_a = alternatives[0] if alternatives else None
        if alternatives:
            best_a = max(alternatives, key=_sort_key)

        # Batch A always evaluates the critical-fail rule, even when caller
        # passes never_replace=True (legacy "preserve mirror" intent now means
        # "preserve UNLESS mirror is already broken").
        if post.batch == "A":
            should_apply, apply_reason = _should_apply_batch_a_variant(post, best_a)
        else:
            should_apply, apply_reason = (False, "never_replace")

        if should_apply:
            post = _apply_best_opener(post, best_a)
            post.mechanic = "mirrored"  # keep slot label; A is still A
            post.actual_mechanic = _normalize_mechanic(best_a.get("mechanic", ""))
            post.rating = best_a.get("rating", 0)
            logger.info(
                "[amplifier_batch] %s: Batch A variant APPLIED (reason=%s, actual_mechanic=%s)",
                post.label, apply_reason, post.actual_mechanic,
            )
            replaced = True
        else:
            post.final_opening = post.original_opening
            post.mechanic = "mirrored" if post.batch == "A" else _normalize_mechanic(diag.get("current_mechanic", "kept"))
            post.actual_mechanic = _normalize_mechanic(diag.get("current_mechanic", ""))
            post.rating = 0 if post.batch == "A" else 5
            replaced = False

        state.amplifier_log.append({
            "label": post.label,
            "original": post.original_opening[:100],
            "final": post.final_opening[:100],
            "gates_passed": all(post.gates.values()) if post.gates else True,
            "replaced": replaced,
            "variants_count": len(alternatives),
            "recommended": getattr(post, "recommended_variant", ""),
            "v2": True,
            "batch_mode": True,
            "never_replace": never_replace,
            "batch_a_apply_reason": apply_reason if not replaced else None,
            "batch_a_applied": replaced,
        })
        return post

    if alternatives:
        best = max(alternatives, key=_sort_key)
        best_rating = best.get("rating", 0)

        BASELINE_RATING = 7
        rating_lift = best_rating >= BASELINE_RATING + 1
        variant_safe = (best.get("coherence_with_body", True) and
                        best.get("plausibility", True) and
                        best.get("voice_fit", True) and
                        best.get("mode_preservation", True))

        door_preserved, preserve_reason = _should_preserve_door(post, diag, best, peers)
        if door_preserved:
            logger.info(
                "[amplifier_batch] %s: door-preserved (reason=%s, entry_door=%s, "
                "best_variant_rating=%d)",
                post.label, preserve_reason, post.entry_door, best_rating,
            )

        if not door_preserved and ((not all_pass) or is_slop or (rating_lift and variant_safe)):
            apply_reason = (
                "gate_fail" if not all_pass
                else "slop" if is_slop
                else f"rating_lift({best_rating})"
            )
            post = _apply_best_opener(post, best)
            post.actual_mechanic = post.mechanic
            logger.info("[amplifier_batch] %s: replaced opener (mechanic=%s, rating=%d, reason=%s)",
                        post.label, post.mechanic, post.rating, apply_reason)
        else:
            post.final_opening = post.original_opening
            post.mechanic = _normalize_mechanic(diag.get("current_mechanic", "kept"))
            post.actual_mechanic = post.mechanic
            post.rating = 5
    else:
        post.final_opening = post.original_opening
        post.mechanic = _normalize_mechanic(diag.get("current_mechanic", "kept"))
        post.actual_mechanic = post.mechanic
        post.rating = 5

    state.amplifier_log.append({
        "label": post.label,
        "original": post.original_opening[:100],
        "final": post.final_opening[:100],
        "gates_passed": all(post.gates.values()) if post.gates else True,
        "replaced": post.original_opening != post.final_opening,
        "variants_count": len(alternatives),
        "recommended": getattr(post, "recommended_variant", ""),
        "v2": True,
        "batch_mode": True,
    })

    return post


def convergence_test(
    llm: LLMProvider,
    pack_posts: list[AmplifiedPost],
    source_summary: str,
    state: BatchState,
) -> dict:
    """v5 shim: convergence is now part of validate_pack (05_validate.txt).
    Returns PASS so legacy callers in session.py don't trigger a regen loop
    during the transition. The real convergence check lives in
    voice_validator.validate_pack().
    """
    return {
        "passed": True,
        "recommendation": "(v5: convergence merged into 05_validate.txt pack-level call)",
        "overlapping_posts": [],
        "replacement_angles": [],
    }
