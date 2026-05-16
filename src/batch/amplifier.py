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


def diagnose_opener(llm: LLMProvider, post: AmplifiedPost, state: BatchState, source_dissection: dict | None = None) -> dict:
    """Run 7-gate diagnosis on a post's opening line (Gate 7 for Batch A only)."""
    if getattr(state, "llm_router", None):
        llm = state.llm_router.for_task("amplifier_diagnose")
    template = load_prompt(PROMPTS_DIR / "amplifier_diagnose.txt")
    source_diss_str = "N/A"
    source_mechanic = "N/A"
    source_body_format = "N/A"
    source_closer_mechanic = "N/A"
    if source_dissection:
        source_diss_str = str(source_dissection)[:800]
        source_mechanic = source_dissection.get("hook_mechanic_primary", "unknown")
        source_body_format = source_dissection.get("body_format") or "prose_essay"
        source_closer_mechanic = source_dissection.get("closer_mechanic") or "terminal_verdict"
    prompt = fill_prompt(
        template,
        post_text=post.text,
        voice_markers="\n".join(f"- {m}" for m in state.voice_markers),
        mode=post.mode,
        source_dissection=source_diss_str,
        source_hook_mechanic=source_mechanic,
        source_body_format=source_body_format,
        source_closer_mechanic=source_closer_mechanic,
    )

    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=0.2, max_tokens=4000)
    _dur = int((_t.time() - _start) * 1000)
    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage=f"amplifier_diagnose_{post.label}",
            template="amplifier_diagnose.txt",
            prompt=prompt,
            response=response,
            temperature=0.2,
            max_tokens=4000,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
            metadata={"post_label": post.label, "mode": post.mode},
        )

    if not isinstance(result, dict) or not result:
        logger.warning("[amplifier] diagnose JSON parse failed for %s, raw: %.300s", post.label, response)
        import re as _re
        json_match = _re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                result = json.loads(json_match.group())
            except (json.JSONDecodeError, ValueError):
                pass
        if not isinstance(result, dict) or not result:
            return {"all_gates_pass": True, "current_mechanic": "unclear", "buried_gold": "", "weakness": "", "gates": {}}

    return result


def generate_alternatives(
    llm: LLMProvider,
    post: AmplifiedPost,
    diagnosis: dict,
    state: BatchState,
) -> list[dict]:
    """Generate exactly 5 replacement opening lines (variants A-E) using different mechanics."""
    if getattr(state, "llm_router", None):
        llm = state.llm_router.for_task("amplifier_generate")
    template = load_prompt(PROMPTS_DIR / "amplifier_generate.txt")
    prompt = fill_prompt(
        template,
        post_text=post.text,
        diagnosis=str(diagnosis)[:1000],
        buried_gold=diagnosis.get("buried_gold", ""),
        voice_markers="\n".join(f"- {m}" for m in state.voice_markers),
        mode=post.mode,
    )

    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=0.5, max_tokens=4000)
    _dur = int((_t.time() - _start) * 1000)
    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage=f"amplifier_generate_{post.label}",
            template="amplifier_generate.txt",
            prompt=prompt,
            response=response,
            temperature=0.5,
            max_tokens=4000,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
            metadata={"post_label": post.label},
        )

    variants_list = []
    if isinstance(result, dict) and "variants" in result:
        variants_list = result.get("variants", [])
    elif isinstance(result, list):
        variants_list = result

    valid = []
    letters = ["A", "B", "C", "D", "E"]
    for i, v in enumerate(variants_list):
        if not isinstance(v, dict) or "opening" not in v:
            continue
        if _is_slop(v["opening"]):
            continue
        v["variant"] = v.get("variant", letters[i] if i < 5 else f"X{i}")
        v["mechanic"] = _normalize_mechanic(v.get("mechanic", ""))
        valid.append(v)

    return valid


def _apply_best_opener(post: AmplifiedPost, best: dict) -> AmplifiedPost:
    """Replace the post's opening paragraph with the best alternative."""
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


def amplify_post(
    llm: LLMProvider,
    post: AmplifiedPost,
    pack_posts: list[AmplifiedPost],
    state: BatchState,
    llm_prep: LLMProvider | None = None,
    source_dissection: dict | None = None,
) -> AmplifiedPost:
    """Full amplifier pass on a single post: diagnose → generate → select best.

    llm is the generation model (Opus) for writing alternatives.
    llm_prep is the lightweight model (Haiku) for diagnosis. Falls back to llm.
    """
    logger.info("[amplifier] Processing %s...", post.label)

    diagnosis = diagnose_opener(llm_prep or llm, post, state, source_dissection=source_dissection)
    if not diagnosis.get("buried_gold") and not diagnosis.get("weakness"):
        logger.warning("[amplifier] %s: diagnosis returned no buried_gold/weakness — possible parse failure", post.label)
    post.original_opening = post.text.strip().split("\n\n")[0] if post.text else ""

    gates = diagnosis.get("gates", {})
    post.gates = {k: v.get("pass", True) if isinstance(v, dict) else v for k, v in gates.items()}
    post.buried_gold = diagnosis.get("buried_gold", "")
    post.weakness = diagnosis.get("weakness", "")

    all_pass = diagnosis.get("all_gates_pass", True)
    gate7_fail_reason = ""
    if source_dissection:
        gate7 = gates.get("source_mirror", {})
        if isinstance(gate7, dict) and not gate7.get("pass", True):
            all_pass = False
            failed_subchecks = []
            if not gate7.get("mechanic_match", True):
                failed_subchecks.append("mechanic")
            if not gate7.get("body_format_match", True):
                failed_subchecks.append(f"body_format(actual={gate7.get('body_format_actual', '?')})")
            if not gate7.get("closer_mechanic_match", True):
                failed_subchecks.append(f"closer(actual={gate7.get('closer_mechanic_actual', '?')})")
            gate7_fail_reason = ",".join(failed_subchecks) or "unspecified"
            logger.info("[amplifier] %s: Gate 7 (source mirror) FAIL — %s", post.label, gate7_fail_reason)
    is_slop = _is_slop(post.original_opening)

    alternatives = generate_alternatives(llm, post, diagnosis, state)
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
        best_rating = best.get("rating", 0)

        # Apply rebuild when: gates failed, slop detected, or the recommended variant
        # is materially better than baseline (rating >= 8). Without this, the amplifier
        # recommends a variant but ships the original — the "Recommended: C but Final
        # Opening unchanged" failure mode.
        BASELINE_RATING = 7
        rating_lift = best_rating >= BASELINE_RATING + 1
        coh_ok = best.get("coherence_with_body", True)
        plaus_ok = best.get("plausibility", True)
        vfit_ok = best.get("voice_fit", True)
        mode_ok = best.get("mode_preservation", True)
        variant_safe = coh_ok and plaus_ok and vfit_ok and mode_ok

        if (not all_pass) or is_slop or (rating_lift and variant_safe):
            apply_reason = (
                f"gate_fail({gate7_fail_reason})" if not all_pass and gate7_fail_reason
                else "gate_fail" if not all_pass
                else "slop" if is_slop
                else f"rating_lift({best_rating})"
            )
            post = _apply_best_opener(post, best)
            logger.info("[amplifier] %s: replaced opener (mechanic=%s, rating=%d, reason=%s)",
                        post.label, post.mechanic, post.rating, apply_reason)
        else:
            post.final_opening = post.original_opening
            post.mechanic = _normalize_mechanic(diagnosis.get("current_mechanic", "kept"))
            post.rating = 5
    else:
        post.final_opening = post.original_opening
        post.mechanic = _normalize_mechanic(diagnosis.get("current_mechanic", "unchanged" if not all_pass else "kept"))
        post.rating = 5 if all_pass else 0

    state.amplifier_log.append({
        "label": post.label,
        "original": post.original_opening[:100],
        "final": post.final_opening[:100],
        "gates_passed": all(post.gates.values()) if post.gates else True,
        "replaced": post.original_opening != post.final_opening,
        "variants_count": len(alternatives),
        "recommended": post.recommended_variant,
    })

    return post


_BATCH_CHUNK_SIZE = 3


def _amplify_chunk(
    llm: LLMProvider,
    chunk: list[AmplifiedPost],
    state: BatchState,
    chunk_idx: int,
) -> dict:
    """Run amplifier on a small chunk of posts, return label->result map."""
    template = load_prompt(PROMPTS_DIR / "amplifier_batch.txt")

    posts_block = "\n".join(
        f"### POST: {p.label} (mode: {p.mode})\n{p.text}\n" for p in chunk
    )
    prompt = fill_prompt(
        template,
        posts_block=posts_block,
        voice_markers="\n".join(f"- {m}" for m in state.voice_markers),
    )

    import time as _t
    _start = _t.time()
    try:
        response = llm.generate(prompt, temperature=0.5, max_tokens=llm.max_output_tokens)
    except Exception as e:
        logger.warning("[amplifier] chunk %d API error (%s), skipping", chunk_idx, e)
        return {}
    _dur = int((_t.time() - _start) * 1000)
    parsed = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage=f"amplifier_batch_chunk_{chunk_idx}",
            template="amplifier_batch.txt",
            prompt=prompt,
            response=response,
            temperature=0.5,
            max_tokens=llm.max_output_tokens,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
            metadata={"post_count": len(chunk), "chunk": chunk_idx, "lean": True},
        )

    amp_results = []
    if isinstance(parsed, dict) and "posts" in parsed:
        amp_results = parsed["posts"]
    elif isinstance(parsed, list):
        amp_results = parsed

    return {r["label"]: r for r in amp_results if isinstance(r, dict) and r.get("label")}


def amplify_batch(
    llm: LLMProvider,
    posts: list[AmplifiedPost],
    state: BatchState,
    source_dissection: dict | None = None,
) -> list[AmplifiedPost]:
    """Lean mode: diagnose + generate 5 opener variants per post.

    Chunks posts into groups of 3 so the LLM reliably produces all 5
    variants A-E per post (9 posts × 5 variants in one call is too much
    output and the LLM collapses to a single best_alternative).
    """
    if getattr(state, "llm_router", None):
        llm = state.llm_router.for_task("amplifier_batch")

    chunks = [posts[i:i + _BATCH_CHUNK_SIZE] for i in range(0, len(posts), _BATCH_CHUNK_SIZE)]
    label_to_result: dict = {}
    for ci, chunk in enumerate(chunks):
        label_to_result.update(_amplify_chunk(llm, chunk, state, ci))

    for post in posts:
        r = label_to_result.get(post.label)
        if not r:
            post.final_opening = post.text.strip().split("\n\n")[0] if post.text else ""
            post.original_opening = post.final_opening
            post.mechanic = "kept"
            post.rating = 5
            continue

        post.original_opening = post.text.strip().split("\n\n")[0] if post.text else ""
        post.buried_gold = r.get("buried_gold", "")
        post.weakness = r.get("weakness", "")

        alternatives = r.get("variants", [])
        if isinstance(alternatives, list) and alternatives:
            post.opener_variants = alternatives
            post.versions_considered = len(alternatives)
        else:
            best_alt = r.get("best_alternative")
            if isinstance(best_alt, dict) and best_alt.get("opening"):
                post.opener_variants = [{**best_alt, "variant": "A"}]
                post.versions_considered = 1
                alternatives = post.opener_variants
                logger.info("[amplifier_batch] %s: LLM returned best_alternative instead of variants array", post.label)
            else:
                logger.warning("[amplifier_batch] %s: no variants and no best_alternative in response", post.label)

        rec_variant = r.get("recommended_variant", "A")
        post.recommended_variant = rec_variant

        should_apply = r.get("apply", False)
        all_pass = r.get("all_gates_pass", True)
        is_slop = _is_slop(post.original_opening)

        if alternatives:
            def _sort_key(v):
                coh = 1 if v.get("coherence_with_body", True) else 0
                plaus = 1 if v.get("plausibility", True) else 0
                vfit = 1 if v.get("voice_fit", True) else 0
                mode_fit = 1 if v.get("mode_preservation", True) else 0
                rating = v.get("rating", 0)
                return (coh, plaus, vfit, mode_fit, rating)

            best = None
            for v in alternatives:
                if v.get("variant") == rec_variant:
                    best = v
                    break
            if not best:
                best = max(alternatives, key=_sort_key)

            coh = best.get("coherence_with_body", True)
            plaus = best.get("plausibility", True)
            vfit = best.get("voice_fit", True)
            mode_ok = best.get("mode_preservation", True)
            rating = best.get("rating", 0)

            if (should_apply or not all_pass or is_slop or rating >= 8) and coh and plaus and vfit and mode_ok:
                post = _apply_best_opener(post, best)
                logger.info("[amplifier_batch] %s: replaced opener (variant=%s, mechanic=%s, rating=%d)",
                            post.label, best.get("variant", "?"), post.mechanic, post.rating)
            else:
                post.final_opening = post.original_opening
                post.mechanic = _normalize_mechanic(r.get("current_mechanic", "kept"))
                post.rating = rating or 5
        else:
            post.final_opening = post.original_opening
            post.mechanic = _normalize_mechanic(r.get("current_mechanic", "kept"))
            post.rating = 5

        state.amplifier_log.append({
            "label": post.label,
            "original": post.original_opening[:100],
            "final": post.final_opening[:100],
            "gates_passed": r.get("all_gates_pass", True),
            "replaced": post.original_opening != post.final_opening,
            "variants_count": len(post.opener_variants),
            "lean": True,
        })

    return posts


def convergence_test(
    llm: LLMProvider,
    pack_posts: list[AmplifiedPost],
    source_summary: str,
    state: BatchState,
) -> dict:
    """Test whether posts in a pack argue too-similar things."""
    if getattr(state, "llm_router", None):
        llm = state.llm_router.for_task("convergence_test")
    if len(pack_posts) < 3:
        return {"passed": True, "recommendation": "too few posts to test"}

    arguments = "\n".join(
        f"- {p.label}: {p.argument_compressed}" for p in pack_posts if p.argument_compressed
    )

    if not arguments.strip():
        return {"passed": True, "recommendation": "no arguments to compare"}

    template = load_prompt(PROMPTS_DIR / "amplifier_convergence.txt")
    prompt = fill_prompt(
        template,
        arguments=arguments,
        source_summary=source_summary[:500],
    )

    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=0.2, max_tokens=1000)
    _dur = int((_t.time() - _start) * 1000)
    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage="convergence_test",
            template="amplifier_convergence.txt",
            prompt=prompt,
            response=response,
            temperature=0.2,
            max_tokens=1000,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
            metadata={"posts_count": len(pack_posts)},
        )

    if not isinstance(result, dict):
        return {"passed": True, "recommendation": "convergence test parse failed"}

    return result
