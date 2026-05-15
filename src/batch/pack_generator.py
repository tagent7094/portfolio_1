"""9-post pack generator — 3 Batch A (mirrored) + 6 Batch B (mechanics-only)."""

from __future__ import annotations

import logging
from pathlib import Path

from ..utils.json_parser import parse_llm_json
from ..utils.text_utils import load_prompt, fill_prompt
from ..llm.base import LLMProvider
from ..generation.creativity import creativity_to_temperature
from .state import BatchState, PackResult, AmplifiedPost

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).parent / "prompts"

ENTRY_DOORS = [
    "scene_drop",
    "diagnostic_question",
    "borrowed_authority_quote",
    "data_contradiction",
    "confession",
    "physical_object",
    "direct_address",
    "mocked_counter_example",
    "contrarian_claim",
    "parallel_structure",
    "age_time_anchor",
    "second_party_verdict",
]


def dissect_source(llm: LLMProvider, source: str, state: BatchState, pack_num: int = 0) -> dict:
    """Dissect a viral source post's hook mechanics."""
    if getattr(state, "llm_router", None):
        llm = state.llm_router.for_task("dissect")
    template = load_prompt(PROMPTS_DIR / "source_dissect_hook.txt")
    prompt = fill_prompt(template, source_post=source, platform=state.platform)

    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=0.2, max_tokens=2000)
    _dur = int((_t.time() - _start) * 1000)
    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage=f"pack_{pack_num}_dissect",
            template="source_dissect_hook.txt",
            prompt=prompt,
            response=response,
            temperature=0.2,
            max_tokens=2000,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
        )

    return result if isinstance(result, dict) else {"narrative_arc": "unknown", "mirrorable": True}


def verify_opener_tests(dissection: dict) -> dict:
    """Verify opener quality tests from dissection and enforce skip_batch_a gating."""
    tests = dissection.get("opener_tests")
    if not isinstance(tests, dict):
        return dissection

    failed = []
    for test_name in ("macro", "fast", "simple"):
        test = tests.get(test_name)
        if isinstance(test, dict) and not test.get("pass", True):
            failed.append(test_name)

    if failed:
        dissection["skip_batch_a"] = True
        logger.info("[batch] Opener tests failed: %s → skip_batch_a=True", ", ".join(failed))

    return dissection


def _format_opener_tests(dissection: dict) -> str:
    """Format opener quality tests from dissection for prompt insertion."""
    tests = dissection.get("opener_tests")
    if not isinstance(tests, dict):
        return "No opener tests available."
    parts = []
    for name in ("macro", "fast", "simple"):
        test = tests.get(name)
        if isinstance(test, dict):
            status = "PASS" if test.get("pass", True) else "FAIL"
            reason = test.get("reason", "")
            parts.append(f"- {name.upper()}: {status} — {reason}")
    return "\n".join(parts) if parts else "No opener tests available."


def _format_internalization(state: BatchState) -> str:
    """Format internalization data for prompt insertion."""
    intern = state.founder_internalization
    parts = []
    if intern.get("tensions"):
        parts.append("TENSIONS:\n" + "\n".join(f"- {t}" for t in intern["tensions"][:8]))
    if intern.get("signature_scenes"):
        parts.append("SCENES:\n" + "\n".join(f"- {s}" for s in intern["signature_scenes"][:10]))
    if intern.get("argument_rhythm"):
        parts.append(f"RHYTHM: {intern['argument_rhythm']}")
    if intern.get("key_moments_inventory"):
        parts.append("KEY MOMENTS:\n" + "\n".join(f"- {k}" for k in intern["key_moments_inventory"][:15]))
    if intern.get("recurring_cast"):
        parts.append("CAST:\n" + "\n".join(f"- {c}" for c in intern["recurring_cast"][:10]))
    return "\n\n".join(parts) if parts else "No internalization data available."


def _generate_a_variant(
    llm: LLMProvider,
    source: str,
    dissection: dict,
    variant_num: int,
    state: BatchState,
    prior_a_posts: list[AmplifiedPost] | None = None,
) -> AmplifiedPost:
    """Generate one Batch A (mirrored opening) post."""
    if getattr(state, "llm_router", None):
        llm = state.llm_router.for_task("generate_a")
    template = load_prompt(PROMPTS_DIR / "generate_pack_a.txt")
    temp = creativity_to_temperature(state.creativity)

    events_str = "\n".join(f"- {e}" for e in sorted(state.events_used_global)[:50]) or "None yet"
    stories_str = "\n".join(f"- {s}" for s in sorted(state.stories_used_global)[:30]) or "None yet"

    prior_str = "None yet — this is the first A variant."
    if prior_a_posts:
        parts = []
        for p in prior_a_posts:
            opener = p.text.strip().split("\n\n")[0][:200] if p.text else ""
            parts.append(f"- A{prior_a_posts.index(p)+1}: {opener}")
        prior_str = "\n".join(parts)

    source_cast = ", ".join(dissection.get("named_entities", [])) or "None extracted"

    source_hook_mechanic = dissection.get("hook_mechanic_primary", "unknown")
    source_mechanic_description = dissection.get("opener_mechanic_description", "Not available — mirror based on hook_mechanics array")
    source_opener_sentences = [
        hm["sentence"] for hm in dissection.get("hook_mechanics", [])
        if isinstance(hm, dict) and hm.get("sentence")
    ]
    source_opener_text = "\n".join(source_opener_sentences) if source_opener_sentences else dissection.get("source_opener_text", "")
    source_body_format = dissection.get("body_format") or "prose_essay"
    source_body_item_count = str(dissection.get("body_item_count") or "n/a")
    source_closer_mechanic = dissection.get("closer_mechanic") or "terminal_verdict"
    source_closer_text = dissection.get("closer_text") or "(not extracted)"

    prompt = fill_prompt(
        template,
        source_post=source,
        dissection=str(dissection)[:1000],
        internalization=_format_internalization(state),
        voice_markers="\n".join(f"- {m}" for m in state.voice_markers),
        personality_card=state.personality_card[:2000],
        word_count_range=f"{state.word_count_range[0]}-{state.word_count_range[1]} words",
        formatting_habits=str(state.formatting_habits),
        events_used=events_str,
        stories_used=stories_str,
        variant_number=str(variant_num),
        prior_a_posts=prior_str,
        opener_tests=_format_opener_tests(dissection),
        source_cast=source_cast,
        source_hook_mechanic=source_hook_mechanic,
        source_mechanic_description=source_mechanic_description,
        source_opener_text=source_opener_text,
        source_body_format=source_body_format,
        source_body_item_count=source_body_item_count,
        source_closer_mechanic=source_closer_mechanic,
        source_closer_text=source_closer_text,
    )

    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=temp, max_tokens=3000)
    _dur = int((_t.time() - _start) * 1000)
    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage=f"generate_a{variant_num}",
            template="generate_pack_a.txt",
            prompt=prompt,
            response=response,
            temperature=temp,
            max_tokens=2000,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
            metadata={"variant": variant_num, "batch": "A"},
        )

    if not isinstance(result, dict) or not result.get("text"):
        logger.warning("[batch] A%d: JSON parse returned no text, using raw response", variant_num)
        return AmplifiedPost(
            label=f"A{variant_num}", batch="A", entry_door="mirrored",
            mode="declaring", text=response[:500],
        )

    if not result.get("structural_match", True):
        logger.info("[batch] A%d: structural mismatch, regenerating once", variant_num)
        _start = _t.time()
        response = llm.generate(prompt, temperature=min(temp + 0.1, 1.0), max_tokens=3000)
        _dur = int((_t.time() - _start) * 1000)
        retry = parse_llm_json(response)
        if isinstance(retry, dict) and retry.get("text"):
            result = retry
        if state.tracer:
            state.tracer.trace_llm_call(
                stage=f"generate_a{variant_num}_retry",
                template="generate_pack_a.txt",
                prompt="(structural mismatch retry)",
                response=response,
                temperature=min(temp + 0.1, 1.0),
                max_tokens=3000,
                duration_ms=_dur,
                thinking=getattr(llm, 'last_thinking', ''),
                metadata={"variant": variant_num, "batch": "A", "retry": True},
            )

    post = AmplifiedPost(
        label=f"A{variant_num}",
        batch="A",
        entry_door="mirrored",
        mode=result.get("mode", "declaring"),
        text=result.get("text", ""),
        word_count=len(result.get("text", "").split()),
        events_used=result.get("events_used", []),
        argument_compressed=result.get("argument_compressed", ""),
    )
    state.events_used_global.update(post.events_used)
    state.stories_used_global.update(result.get("stories_used", []))
    return post


def _generate_b_variant(
    llm: LLMProvider,
    source: str,
    dissection: dict,
    entry_door: str,
    variant_num: int,
    doors_used: list[str],
    state: BatchState,
) -> AmplifiedPost:
    """Generate one Batch B (mechanics-only) post."""
    if getattr(state, "llm_router", None):
        llm = state.llm_router.for_task("generate_b")
    template = load_prompt(PROMPTS_DIR / "generate_pack_b.txt")
    temp = creativity_to_temperature(state.creativity)

    events_str = "\n".join(f"- {e}" for e in sorted(state.events_used_global)[:50]) or "None yet"
    stories_str = "\n".join(f"- {s}" for s in sorted(state.stories_used_global)[:30]) or "None yet"

    source_cast = ", ".join(dissection.get("named_entities", [])) or "None extracted"

    prompt = fill_prompt(
        template,
        source_post=source,
        dissection=str(dissection)[:1000],
        entry_door=entry_door,
        hook_mechanic_primary=dissection.get("hook_mechanic_primary", "unknown"),
        internalization=_format_internalization(state),
        voice_markers="\n".join(f"- {m}" for m in state.voice_markers),
        personality_card=state.personality_card[:2000],
        word_count_range=f"{state.word_count_range[0]}-{state.word_count_range[1]} words",
        formatting_habits=str(state.formatting_habits),
        events_used=events_str,
        stories_used=stories_str,
        doors_used_in_pack=", ".join(doors_used) if doors_used else "None yet",
        opener_tests=_format_opener_tests(dissection),
        source_cast=source_cast,
    )

    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=temp, max_tokens=3000)
    _dur = int((_t.time() - _start) * 1000)
    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage=f"generate_b{variant_num}",
            template="generate_pack_b.txt",
            prompt=prompt,
            response=response,
            temperature=temp,
            max_tokens=2000,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
            metadata={"variant": variant_num, "batch": "B", "entry_door": entry_door},
        )

    if not isinstance(result, dict) or not result.get("text"):
        logger.warning("[batch] B%d: JSON parse returned no text, using raw response", variant_num)
        return AmplifiedPost(
            label=f"B{variant_num}", batch="B", entry_door=entry_door,
            mode="declaring", text=response[:500],
        )

    post = AmplifiedPost(
        label=f"B{variant_num}",
        batch="B",
        entry_door=entry_door,
        mode=result.get("mode", "declaring"),
        text=result.get("text", ""),
        word_count=len(result.get("text", "").split()),
        events_used=result.get("events_used", []),
        argument_compressed=result.get("argument_compressed", ""),
    )
    state.events_used_global.update(post.events_used)
    state.stories_used_global.update(result.get("stories_used", []))
    return post


def _llm_trim_post(llm: LLMProvider, post: AmplifiedPost, state: BatchState) -> AmplifiedPost:
    """Use LLM to trim a post that mechanical trimming couldn't fix."""
    if getattr(state, "llm_router", None):
        llm = state.llm_router.for_task("word_count_trim")
    _lo, _hi = state.word_count_range
    lo, hi = min(_lo, _hi), max(_lo, _hi)
    prompt = f"""This LinkedIn post is {post.word_count} words. The target range is {lo}-{hi} words.

Trim it to fit by removing the least essential paragraph. Rules:
- Keep the opening paragraph exactly as-is
- Keep the closing paragraph exactly as-is
- Remove or shorten middle paragraphs
- Preserve the core argument

Return ONLY the trimmed post text, no JSON wrapping, no explanation.""" + f"\n\n---\n\n{post.text}"

    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=0.2, max_tokens=2000)
    _dur = int((_t.time() - _start) * 1000)

    trimmed = response.strip()
    new_wc = len(trimmed.split())
    if lo <= new_wc <= hi:
        old_wc = post.word_count
        post.text = trimmed
        post.word_count = new_wc
        logger.info("[batch] LLM-trimmed %s from %d to %d words", post.label, old_wc, new_wc)
    else:
        logger.warning("[batch] LLM trim for %s produced %d words (wanted %d-%d), keeping original",
                       post.label, new_wc, lo, hi)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage=f"word_count_trim_{post.label}",
            template="(inline word-count trim)",
            prompt=prompt,
            response=response,
            temperature=0.2,
            max_tokens=2000,
            duration_ms=_dur,
            thinking="",
            metadata={"original_wc": post.word_count, "target": f"{lo}-{hi}"},
        )

    return post


def _enforce_word_count(post: AmplifiedPost, state: BatchState, llm: LLMProvider | None = None) -> AmplifiedPost:
    """Enforce word count range: mechanical trim → LLM retry → flag violation."""
    _lo, _hi = state.word_count_range
    lo, hi = min(_lo, _hi), max(_lo, _hi)
    wc = post.word_count
    if lo <= wc <= hi:
        return post
    if wc > hi:
        paragraphs = post.text.strip().split("\n\n")
        if len(paragraphs) > 3:
            paragraphs.pop(-2)
            post.text = "\n\n".join(paragraphs)
            post.word_count = len(post.text.split())
            logger.info("[batch] Trimmed %s from %d to %d words", post.label, wc, post.word_count)
    if lo <= post.word_count <= hi:
        return post
    if post.word_count > hi and llm:
        post = _llm_trim_post(llm, post, state)
    if lo <= post.word_count <= hi:
        return post
    violation = f"word_count: {post.word_count} (range {lo}-{hi})"
    post.violations.append(violation)
    if post.word_count < lo:
        logger.warning("[batch] %s VIOLATION: %s", post.label, violation)
    else:
        logger.warning("[batch] %s VIOLATION: %s — flagged for review", post.label, violation)
    return post


def select_entry_doors(n: int, used_globally: dict, pack_number: int) -> list[str]:
    """Select n unique entry doors for Batch B, avoiding recent repetition."""
    used_in_recent = set()
    for pn in range(max(1, pack_number - 2), pack_number):
        used_in_recent.update(used_globally.get(pn, []))

    available = [d for d in ENTRY_DOORS if d not in used_in_recent]
    if len(available) < n:
        available = list(ENTRY_DOORS)

    selected = available[:n]
    while len(selected) < n:
        for d in ENTRY_DOORS:
            if d not in selected:
                selected.append(d)
                if len(selected) >= n:
                    break
    return selected


def generate_pack(
    llm: LLMProvider,
    source: str,
    pack_number: int,
    state: BatchState,
    posts_per_source: int = 9,
    event_callback=None,
    llm_prep: LLMProvider | None = None,
) -> PackResult:
    """Generate posts for one source. posts_per_source controls the total count.

    llm is the generation model (Opus). llm_prep is the lightweight analysis model (Haiku)
    used for source dissection. Falls back to llm if llm_prep is not provided.
    """
    logger.info("[batch] Generating pack %d (%d posts)...", pack_number, posts_per_source)

    posts_per_source = max(1, min(posts_per_source, 9))

    dissection = dissect_source(llm_prep or llm, source, state, pack_num=pack_number)
    dissection = verify_opener_tests(dissection)
    state.source_dissections.append(dissection)
    mirrorable = dissection.get("mirrorable", True) and not dissection.get("skip_batch_a", False)

    if event_callback:
        event_callback(f"pack_{pack_number}_dissected", {
            "hook_mechanic": dissection.get("hook_mechanic_primary", "unknown"),
            "mirrorable": mirrorable,
        })

    posts: list[AmplifiedPost] = []

    if mirrorable:
        n_a = min(3, posts_per_source)
        a_posts: list[AmplifiedPost] = []
        for i in range(1, n_a + 1):
            logger.info("[batch] Pack %d: generating A%d...", pack_number, i)
            post = _generate_a_variant(llm, source, dissection, i, state, prior_a_posts=a_posts)
            post = _enforce_word_count(post, state, llm=llm)
            posts.append(post)
            a_posts.append(post)
            if event_callback:
                event_callback(f"pack_{pack_number}_a{i}", {"word_count": post.word_count})
        n_b = max(0, posts_per_source - n_a)
    else:
        n_b = posts_per_source

    doors = select_entry_doors(n_b, state.entry_doors_used, pack_number)
    state.entry_doors_used[pack_number] = doors

    doors_used_so_far: list[str] = []
    for i in range(1, n_b + 1):
        door = doors[i - 1]
        logger.info("[batch] Pack %d: generating B%d (door: %s)...", pack_number, i, door)
        post = _generate_b_variant(llm, source, dissection, door, i, doors_used_so_far, state)
        post = _enforce_word_count(post, state, llm=llm)
        posts.append(post)
        doors_used_so_far.append(door)
        if event_callback:
            event_callback(f"pack_{pack_number}_b{i}", {
                "door": door, "word_count": post.word_count,
            })

    n_a_actual = len([p for p in posts if p.batch == "A"])
    return PackResult(
        source_number=pack_number,
        source_post=source,
        dissection=dissection,
        mirrorable=mirrorable,
        posts=posts,
        batch_a_count=n_a_actual,
        batch_b_count=n_b,
    )
