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
    template = load_prompt(PROMPTS_DIR / "source_dissect_hook.txt")
    prompt = fill_prompt(template, source_post=source[:2000], platform=state.platform)

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
) -> AmplifiedPost:
    """Generate one Batch A (mirrored opening) post."""
    template = load_prompt(PROMPTS_DIR / "generate_pack_a.txt")
    temp = creativity_to_temperature(state.creativity)

    events_str = "\n".join(f"- {e}" for e in sorted(state.events_used_global)[:50]) or "None yet"
    stories_str = "\n".join(f"- {s}" for s in sorted(state.stories_used_global)[:30]) or "None yet"

    prompt = fill_prompt(
        template,
        source_post=source[:1500],
        dissection=str(dissection)[:1000],
        internalization=_format_internalization(state),
        voice_markers="\n".join(f"- {m}" for m in state.voice_markers),
        personality_card=state.personality_card[:1500],
        word_count_range=f"{state.word_count_range[0]}-{state.word_count_range[1]} words",
        formatting_habits=str(state.formatting_habits),
        events_used=events_str,
        stories_used=stories_str,
        variant_number=str(variant_num),
    )

    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=temp, max_tokens=2000)
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

    if not isinstance(result, dict):
        return AmplifiedPost(
            label=f"A{variant_num}", batch="A", entry_door="mirrored",
            mode="declaring", text=response[:500],
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
    template = load_prompt(PROMPTS_DIR / "generate_pack_b.txt")
    temp = creativity_to_temperature(state.creativity)

    events_str = "\n".join(f"- {e}" for e in sorted(state.events_used_global)[:50]) or "None yet"
    stories_str = "\n".join(f"- {s}" for s in sorted(state.stories_used_global)[:30]) or "None yet"

    prompt = fill_prompt(
        template,
        source_post=source[:1500],
        dissection=str(dissection)[:1000],
        entry_door=entry_door,
        hook_mechanic_primary=dissection.get("hook_mechanic_primary", "unknown"),
        internalization=_format_internalization(state),
        voice_markers="\n".join(f"- {m}" for m in state.voice_markers),
        personality_card=state.personality_card[:1500],
        word_count_range=f"{state.word_count_range[0]}-{state.word_count_range[1]} words",
        formatting_habits=str(state.formatting_habits),
        events_used=events_str,
        stories_used=stories_str,
        doors_used_in_pack=", ".join(doors_used) if doors_used else "None yet",
    )

    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=temp, max_tokens=2000)
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

    if not isinstance(result, dict):
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
) -> PackResult:
    """Generate posts for one source. posts_per_source controls the total count."""
    logger.info("[batch] Generating pack %d (%d posts)...", pack_number, posts_per_source)

    posts_per_source = max(1, min(posts_per_source, 9))

    dissection = dissect_source(llm, source, state, pack_num=pack_number)
    state.source_dissections.append(dissection)
    mirrorable = dissection.get("mirrorable", True)

    if event_callback:
        event_callback(f"pack_{pack_number}_dissected", {
            "hook_mechanic": dissection.get("hook_mechanic_primary", "unknown"),
            "mirrorable": mirrorable,
        })

    posts: list[AmplifiedPost] = []

    if mirrorable:
        n_a = min(3, posts_per_source)
        for i in range(1, n_a + 1):
            logger.info("[batch] Pack %d: generating A%d...", pack_number, i)
            post = _generate_a_variant(llm, source, dissection, i, state)
            posts.append(post)
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
