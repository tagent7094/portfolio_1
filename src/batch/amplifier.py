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


def diagnose_opener(llm: LLMProvider, post: AmplifiedPost, state: BatchState) -> dict:
    """Run 5-gate diagnosis on a post's opening line."""
    template = load_prompt(PROMPTS_DIR / "amplifier_diagnose.txt")
    prompt = fill_prompt(
        template,
        post_text=post.text,
        voice_markers="\n".join(f"- {m}" for m in state.voice_markers),
        mode=post.mode,
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
) -> AmplifiedPost:
    """Full amplifier pass on a single post: diagnose → generate → select best.

    llm is the generation model (Opus) for writing alternatives.
    llm_prep is the lightweight model (Haiku) for diagnosis. Falls back to llm.
    """
    logger.info("[amplifier] Processing %s...", post.label)

    diagnosis = diagnose_opener(llm_prep or llm, post, state)
    if not diagnosis.get("buried_gold") and not diagnosis.get("weakness"):
        logger.warning("[amplifier] %s: diagnosis returned no buried_gold/weakness — possible parse failure", post.label)
    post.original_opening = post.text.strip().split("\n\n")[0] if post.text else ""

    gates = diagnosis.get("gates", {})
    post.gates = {k: v.get("pass", True) if isinstance(v, dict) else v for k, v in gates.items()}
    post.buried_gold = diagnosis.get("buried_gold", "")
    post.weakness = diagnosis.get("weakness", "")

    all_pass = diagnosis.get("all_gates_pass", True)
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

        if not all_pass or is_slop:
            post = _apply_best_opener(post, best)
            logger.info("[amplifier] %s: replaced opener (mechanic=%s, rating=%d)",
                        post.label, post.mechanic, post.rating)
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
            thinking=getattr(llm, 'last_thinking', ''),
            metadata={"posts_count": len(pack_posts)},
        )

    if not isinstance(result, dict):
        return {"passed": True, "recommendation": "convergence test parse failed"}

    return result
