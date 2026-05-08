"""5-gate Opening Line Amplifier — diagnose, generate alternatives, test convergence."""

from __future__ import annotations

import logging
from pathlib import Path

from ..utils.json_parser import parse_llm_json
from ..utils.text_utils import load_prompt, fill_prompt
from ..llm.base import LLMProvider
from ..generation.opening_line_massacre import _is_slop, AI_SLOP_PATTERNS
from .state import BatchState, AmplifiedPost

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).parent / "prompts"


def diagnose_opener(llm: LLMProvider, post: AmplifiedPost, state: BatchState) -> dict:
    """Run 5-gate diagnosis on a post's opening line."""
    template = load_prompt(PROMPTS_DIR / "amplifier_diagnose.txt")
    prompt = fill_prompt(
        template,
        post_text=post.text[:2000],
        voice_markers="\n".join(f"- {m}" for m in state.voice_markers),
        mode=post.mode,
    )

    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=0.2, max_tokens=1500)
    _dur = int((_t.time() - _start) * 1000)
    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage=f"amplifier_diagnose_{post.label}",
            template="amplifier_diagnose.txt",
            prompt=prompt,
            response=response,
            temperature=0.2,
            max_tokens=1500,
            duration_ms=_dur,
            metadata={"post_label": post.label, "mode": post.mode},
        )

    if not isinstance(result, dict):
        return {"all_gates_pass": True, "current_mechanic": "unclear", "buried_gold": ""}

    return result


def generate_alternatives(
    llm: LLMProvider,
    post: AmplifiedPost,
    diagnosis: dict,
    state: BatchState,
) -> list[dict]:
    """Generate 3-5 replacement opening lines using different mechanics."""
    if diagnosis.get("all_gates_pass", True) and not _is_slop(post.text[:100]):
        return []

    template = load_prompt(PROMPTS_DIR / "amplifier_generate.txt")
    prompt = fill_prompt(
        template,
        post_text=post.text[:2000],
        diagnosis=str(diagnosis)[:1000],
        buried_gold=diagnosis.get("buried_gold", ""),
        voice_markers="\n".join(f"- {m}" for m in state.voice_markers),
        mode=post.mode,
    )

    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=0.5, max_tokens=2000)
    _dur = int((_t.time() - _start) * 1000)
    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage=f"amplifier_generate_{post.label}",
            template="amplifier_generate.txt",
            prompt=prompt,
            response=response,
            temperature=0.5,
            max_tokens=2000,
            duration_ms=_dur,
            metadata={"post_label": post.label},
        )

    if not isinstance(result, list):
        return []

    valid = []
    for v in result:
        if not isinstance(v, dict) or "opening" not in v:
            continue
        if _is_slop(v["opening"]):
            continue
        all_pass = all(v.get(g, True) for g in [
            "mode_fit", "plausibility", "coherence_with_body", "specificity", "mode_preservation"
        ])
        if all_pass:
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
    post.mechanic = best.get("mechanic", "")
    post.rating = best.get("rating", 0)
    post.word_count = len(post.text.split())
    return post


def amplify_post(
    llm: LLMProvider,
    post: AmplifiedPost,
    pack_posts: list[AmplifiedPost],
    state: BatchState,
) -> AmplifiedPost:
    """Full amplifier pass on a single post: diagnose → generate → select best."""
    logger.info("[amplifier] Processing %s...", post.label)

    diagnosis = diagnose_opener(llm, post, state)
    post.original_opening = post.text.strip().split("\n\n")[0] if post.text else ""

    gates = diagnosis.get("gates", {})
    post.gates = {k: v.get("pass", True) if isinstance(v, dict) else v for k, v in gates.items()}
    post.buried_gold = diagnosis.get("buried_gold", "")

    all_pass = diagnosis.get("all_gates_pass", True)
    is_slop = _is_slop(post.original_opening)

    if not all_pass or is_slop:
        alternatives = generate_alternatives(llm, post, diagnosis, state)
        post.versions_considered = len(alternatives)

        if alternatives:
            def _sort_key(v):
                coh = 1 if v.get("coherence_with_body", True) else 0
                plaus = 1 if v.get("plausibility", True) else 0
                rating = v.get("rating", 0)
                return (coh, plaus, rating)
            best = max(alternatives, key=_sort_key)
            post = _apply_best_opener(post, best)
            logger.info("[amplifier] %s: replaced opener (mechanic=%s, rating=%d)",
                        post.label, post.mechanic, post.rating)
        else:
            post.final_opening = post.original_opening
            post.mechanic = diagnosis.get("current_mechanic", "unchanged")
    else:
        post.final_opening = post.original_opening
        post.mechanic = diagnosis.get("current_mechanic", "kept")
        post.rating = 5

    state.amplifier_log.append({
        "label": post.label,
        "original": post.original_opening[:100],
        "final": post.final_opening[:100],
        "gates_passed": all(post.gates.values()) if post.gates else True,
        "replaced": post.original_opening != post.final_opening,
    })

    return post


def convergence_test(
    llm: LLMProvider,
    pack_posts: list[AmplifiedPost],
    source_summary: str,
    state: BatchState,
) -> dict:
    """Test whether posts in a pack argue too-similar things."""
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
            metadata={"posts_count": len(pack_posts)},
        )

    if not isinstance(result, dict):
        return {"passed": True, "recommendation": "convergence test parse failed"}

    return result
