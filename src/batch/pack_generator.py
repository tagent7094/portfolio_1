"""9-post pack generator — 3 Batch A (mirrored) + 6 Batch B (mechanics-only).

Uses transpose.txt for consolidated generation (3 posts per call).
Old per-file functions kept for convergence regen compatibility.
"""

from __future__ import annotations

import json
import logging
import re
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

    structural_fails = [t for t in failed if t in ("macro", "fast")]
    if structural_fails:
        dissection["skip_batch_a"] = True
        logger.info("[batch] Opener tests failed: %s → skip_batch_a=True", ", ".join(failed))
    elif failed:
        logger.info("[batch] Opener tests failed: %s (non-structural, A batch still allowed)", ", ".join(failed))

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
    story_bank = state.raw_data.get("raw_story_bank", "")
    if story_bank:
        parts.append("STORY BANK (verified events — use these as first-degree authority anchors):\n" + story_bank[:3000])
    return "\n\n".join(parts) if parts else "No internalization data available."


def _scan_batch_a_for_token_leaks(post: AmplifiedPost, forbidden_tokens: list[str]) -> list[str]:
    """Return the list of forbidden tokens that leaked into the post's opener.
    Empty list = clean. Compares against the first paragraph only (the opener).
    """
    if not forbidden_tokens or not post.text:
        return []
    opener = post.text.split("\n\n")[0]
    opener_lower = opener.lower()
    leaks: list[str] = []
    for tok in forbidden_tokens:
        tok_lower = tok.lower()
        if len(tok_lower) < 3:
            continue
        if tok_lower in opener_lower:
            leaks.append(tok)
    return leaks


_SOURCE_NUMBER_PATTERN = re.compile(
    r"\$\d+(?:\.\d+)?\s*(?:billion|million|thousand|B|M|K|k|m|b)\b|"
    r"\b\d+(?:\.\d+)?\s*(?:billion|million|thousand)\b|"
    r"\b\d+(?:\.\d+)?[BMK]\b",
    re.IGNORECASE,
)


def _extract_forbidden_tokens(dissection: dict, source_post: str) -> list[str]:
    """Compose the FORBIDDEN TOKENS list for Batch A: source's specific numbers
    and named entities. Returns a deduplicated, length-capped list.
    """
    tokens: list[str] = []
    for ent in (dissection.get("named_entities") or []):
        if isinstance(ent, str) and ent.strip() and len(ent) >= 3:
            tokens.append(ent.strip())
    for m in _SOURCE_NUMBER_PATTERN.finditer(source_post or ""):
        tok = m.group(0).strip()
        if tok and tok not in tokens:
            tokens.append(tok)
    seen = set()
    deduped = []
    for t in tokens:
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(t)
    return deduped[:20]


def _build_mode_rules_a(dissection: dict, source_post: str = "") -> str:
    """Build mode-specific rules for Batch A (mirrored structure)."""
    source_hook = dissection.get("hook_mechanic_primary", "unknown")
    source_body = dissection.get("body_format", "prose_essay")
    source_closer = dissection.get("closer_mechanic", "terminal_verdict")
    source_opener_sentences = [
        hm["sentence"] for hm in dissection.get("hook_mechanics", [])
        if isinstance(hm, dict) and hm.get("sentence")
    ]
    source_opener_text = "\n".join(source_opener_sentences) if source_opener_sentences else dissection.get("source_opener_text", "")
    source_sentence_count = len(source_opener_sentences) if source_opener_sentences else dissection.get("sentence_count", 1)
    source_item_count = dissection.get("body_item_count") or "n/a"
    source_closer_text = dissection.get("closer_text", "(not extracted)")
    source_domain = dissection.get("source_domain", "the source post's topic")
    forbidden_tokens = _extract_forbidden_tokens(dissection, source_post)
    forbidden_block = ""
    if forbidden_tokens:
        forbidden_block = (
            "\n\n### FORBIDDEN TOKENS — do NOT copy any of these from source into your opener\n"
            + "\n".join(f"- {t}" for t in forbidden_tokens)
            + "\n\nIf the source says \"$4 billion ARR\" and the founder's documented numbers are different, "
            "use the FOUNDER's number. Never reuse the source's specific dollar amount, company name, "
            "or person name — substitute with founder-specific anchors from FOUNDER INTERNALIZATION."
        )

    return f"""## BATCH A (MIRRORED STRUCTURE) — CRITICAL CONSTRAINTS

Your declaration MUST use:
- mechanic: {source_hook}
- body_format: {source_body}
- closer_mechanic: {source_closer}

### OPENER: WORD-FOR-WORD MIRROR — NON-NEGOTIABLE

Your opening line(s) MUST be the source opener with ONLY these substitutions:
- Replace the audience word (e.g., "Sales leaders" → a relevant audience for this founder)
- Replace specific numbers/metrics with the founder's own numbers from FOUNDER INTERNALIZATION
- Replace domain nouns (e.g., "revenue orgs" → the founder's domain equivalent)
- Keep EVERYTHING ELSE identical — same sentence structure, same punctuation, same rhythm, same word count (±3 words), same word order

SOURCE OPENER (your template — do NOT deviate from this shape):
{source_opener_text}

Source mechanic: {source_hook}
Source sentence count: {source_sentence_count}

WRONG — rewriting the opener:
"Most founders don't have a sales problem. They have a trust delegation problem."
(This is a NEW sentence with a DIFFERENT mechanic. Batch A openers must be surgical edits of the source.)

RIGHT — minimal substitution:
Take the source opener word by word. Replace only domain-specific slots. Keep function words, punctuation, structure.

MECHANIC ENFORCEMENT: Your opener MUST use the SAME mechanic family as the source ({source_hook}). If the source uses audience-address + credential + count, YOUR opener must address an audience + state a credential + promise a count. If the source uses confession, YOUR opener must confess. Do NOT substitute a different mechanic.

SIMILARITY GATE: If your opener shares less than 60% of its words with the source opener, it is a structural failure. Rewrite.

### SOURCE DOMAIN LOCK
The source post argues about: {source_domain}
ALL your posts MUST argue within this same domain. Do NOT drift to adjacent topics. If the source is about sales, argue about sales — not hiring, not product, not fundraising.

### BODY: MUST use `{source_body}` format.
- If numbered_list: your body MUST be a numbered list with actual numbers (1., 2., 3., …). Match item count exactly: {source_item_count} items. Do NOT write flowing prose when the source uses a numbered list.
- If bullet_list: use bullets for each discrete unit. Match item count ±1.
- If parallel_paragraphs: write paragraphs that open with the same shape.
- If three_examples: present three clearly delimited examples.
- If before_after: structure as before → pivot → after.
- If progressive_revelation / single_scene / prose_essay: flowing build is allowed.

### CLOSER: MUST use `{source_closer}` mechanic.
Source closer text: {source_closer_text}
- cta → close with a parallel CTA (founder's own breakdown/playbook/DM offer)
- reframe_question → close with a question that flips the reader's posture
- terminal_verdict → close with a declarative final line
- physical_image → close with a concrete physical detail
- challenge → close with "Stop X. Start Y."
- callback → call back to a phrase from the opening
- unresolved_tension / quiet_admission → match accordingly{forbidden_block}"""


def _build_mode_rules_b(doors: list[str], dissection: dict) -> str:
    """Build mode-specific rules for Batch B (entry-door posts)."""
    hook_mechanic = dissection.get("hook_mechanic_primary", "unknown")
    door_defs = {
        "scene_drop": "Start in the MIDDLE of a specific physical moment. No setup, no context.",
        "diagnostic_question": "Open with a question that makes the reader self-diagnose.",
        "borrowed_authority_quote": "Open with something someone credible said, then react.",
        "data_contradiction": "Two data points that shouldn't both be true.",
        "confession": "Admit something that costs you credibility. Not fake vulnerability.",
        "physical_object": "Anchor on a specific physical thing (laptop, whiteboard, text message).",
        "direct_address": "Talk directly to a specific type of person.",
        "mocked_counter_example": "State the bad version of what people do, then flip.",
        "contrarian_claim": "State something most would disagree with. Earned, not clickbait.",
        "parallel_structure": "Two or three parallel sentences with a twist in the last.",
        "age_time_anchor": "Open with a specific age, date, or time marker that signals real memory.",
        "second_party_verdict": "Someone else's judgment or reaction to your situation.",
    }
    door_lines = []
    for i, door in enumerate(doors, 1):
        desc = door_defs.get(door, door)
        door_lines.append(f"Post {i} entry door: **{door}** — {desc}")

    return f"""## BATCH B (MECHANICS-ONLY) — USE ASSIGNED ENTRY DOORS

Same psychological move as the source ({hook_mechanic}) but FULLY different surface — different sentence count, different phrasing, different imagery, different delivery vehicle.

### ASSIGNED ENTRY DOORS (one per post):
{chr(10).join(door_lines)}

### RULES:
- Psychological MOVE matches source's mechanic ({hook_mechanic}) but expressed through the assigned entry door
- Body format and closer mechanic are YOUR choice (declare them in the declaration)
- Do NOT mirror the source's exact structure — that's Batch A's job
- Each post must use a DIFFERENT entry door from the list above
- If two doors feel functionally similar in execution, differentiate the energy/angle"""


def transpose(
    llm: LLMProvider,
    source: str,
    dissection: dict,
    mode: str,
    state: BatchState,
    doors: list[str] | None = None,
    prior_arguments: list[str] | None = None,
    post_count: int = 3,
    pack_number: int = 0,
    diversity_override: str | None = None,
    regen_hint: str = "",
    mechanic_override: str = "",
) -> list[AmplifiedPost]:
    """Generate posts using the consolidated transpose prompt.

    mode="A": mirrored structure (mechanic, body_format, closer from source)
    mode="B": entry-door posts (different surface, same psychological move)
    """
    if getattr(state, "llm_router", None):
        task = "generate_a" if mode == "A" else "generate_b"
        llm = state.llm_router.for_task(task)

    template = load_prompt(PROMPTS_DIR / "transpose.txt")
    temp = creativity_to_temperature(state.creativity)

    if mode == "A":
        mode_rules = _build_mode_rules_a(dissection, source_post=source)
    else:
        mode_rules = _build_mode_rules_b(doors or ["scene_drop", "contrarian_claim", "confession"], dissection)

    events_str = "\n".join(f"- {e}" for e in sorted(state.events_used_global)[:50]) or "None yet"
    stories_str = "\n".join(f"- {s}" for s in sorted(state.stories_used_global)[:30]) or "None yet"
    prior_args_str = "\n".join(f"- {a}" for a in (prior_arguments or [])) or "None yet — this is the first batch."

    if diversity_override:
        prior_args_str += f"\n\nFORCED ANGLE: This post MUST argue: {diversity_override}"

    if regen_hint:
        prior_args_str += (
            f"\n\n## REGEN GUIDANCE — fix these specific issues from the prior draft\n{regen_hint}"
        )

    if mechanic_override:
        prior_args_str += (
            f"\n\n## AVOID MECHANIC: {mechanic_override}\n"
            f"Use a DIFFERENT opener mechanic from the 13 proven options. "
            f"The pack already has too many posts using {mechanic_override}."
        )

    marker_rates_str = "Not measured"
    if state.marker_rates:
        parts = []
        for k, v in state.marker_rates.items():
            parts.append(f"- {k}: ~{v:.1f} per post")
        marker_rates_str = "\n".join(parts)

    dissection_str = json.dumps(dissection, indent=2, ensure_ascii=False)[:2000] if dissection else "N/A"

    # Compose web-search facts block for the fabrication ladder's Tier 2.
    web_ctx = getattr(state, "web_search_context", {}) or {}
    facts = web_ctx.get("facts") or []
    trending = web_ctx.get("trending_topics") or []
    web_lines: list[str] = []
    for f in facts[:15]:
        if isinstance(f, dict):
            fact = f.get("fact", "").strip()
            source_attr = f.get("source", "").strip()
            if fact:
                line = f"- {fact}"
                if source_attr:
                    line += f"  [source: {source_attr}]"
                web_lines.append(line)
        elif isinstance(f, str) and f.strip():
            web_lines.append(f"- {f.strip()}")
    if trending:
        web_lines.append("")
        web_lines.append("Trending topics: " + ", ".join(str(t) for t in trending[:8]))
    web_search_facts_str = "\n".join(web_lines) or "(no verified real-time facts available — DO NOT invent stats or named events)"

    prompt = fill_prompt(
        template,
        post_count=str(post_count),
        mode=f"{'A (mirrored structure)' if mode == 'A' else 'B (entry-door)'}",
        source_post=source,
        dissection=dissection_str,
        platform=state.platform,
        mode_rules=mode_rules,
        internalization=_format_internalization(state),
        voice_markers="\n".join(f"- {m}" for m in state.voice_markers),
        marker_rates=marker_rates_str,
        personality_card=state.personality_card[:2000],
        calibration_paragraph=getattr(state, 'calibration_paragraph', '') or "(no calibration paragraph available)",
        formatting_habits=str(state.formatting_habits),
        word_count_range=f"{state.word_count_range[0]}-{state.word_count_range[1]} words",
        prior_arguments=prior_args_str,
        events_used=events_str,
        stories_used=stories_str,
        web_search_facts=web_search_facts_str,
    )

    max_tok = min(4000 * post_count, 12000)

    import time as _t
    _start = _t.time()
    try:
        response = llm.generate(prompt, temperature=temp, max_tokens=max_tok)
    except Exception as e:
        logger.warning("[transpose] API error for mode=%s pack=%d: %s", mode, pack_number, e)
        return []
    _dur = int((_t.time() - _start) * 1000)
    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage=f"pack_{pack_number}_transpose_{mode.lower()}",
            template="transpose.txt",
            prompt=prompt,
            response=response,
            temperature=temp,
            max_tokens=max_tok,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
            metadata={"mode": mode, "post_count": post_count, "doors": doors},
        )

    if not isinstance(result, dict) or "posts" not in result:
        logger.warning("[transpose] Parse failed for mode=%s, returning empty", mode)
        return []

    posts = []
    for i, p in enumerate(result.get("posts", [])[:post_count], start=1):
        if not isinstance(p, dict) or not p.get("text"):
            continue

        label = f"{'A' if mode == 'A' else 'B'}{i}"
        entry_door = "mirrored" if mode == "A" else (doors[i - 1] if doors and i <= len(doors) else "unknown")

        declaration = p.get("declaration", {})

        # Validate declaration matches source for Batch A
        if mode == "A" and declaration:
            expected_body = dissection.get("body_format", "")
            actual_body = declaration.get("body_format", "")
            if expected_body and actual_body and expected_body != actual_body:
                logger.warning("[transpose] A%d: declaration body_format=%s != source %s",
                             i, actual_body, expected_body)

        post = AmplifiedPost(
            label=label,
            batch=mode[0] if mode else "B",
            entry_door=entry_door,
            mode=p.get("mode", "declaring"),
            text=p.get("text", ""),
            word_count=len(p.get("text", "").split()),
            events_used=p.get("events_used", []),
            argument_compressed=declaration.get("argument_compressed", p.get("argument_compressed", "")),
        )

        state.events_used_global.update(post.events_used)
        stories = p.get("stories_used", [])
        state.stories_used_global.update(stories)
        for story in stories:
            if story:
                state.story_usage_counter[story] = state.story_usage_counter.get(story, 0) + 1

        posts.append(post)

    logger.info("[transpose] mode=%s produced %d/%d posts", mode, len(posts), post_count)
    return posts


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

    max_tok = llm.max_output_tokens

    import time as _t
    _start = _t.time()
    try:
        response = llm.generate(prompt, temperature=0.2, max_tokens=max_tok)
    except Exception as e:
        logger.warning("[batch] LLM trim API error for %s (%s), keeping original", post.label, e)
        return post
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
            max_tokens=max_tok,
            duration_ms=_dur,
            thinking="",
            metadata={"original_wc": post.word_count, "target": f"{lo}-{hi}"},
        )

    return post


def _enforce_word_count(post: AmplifiedPost, state: BatchState, llm: LLMProvider | None = None) -> AmplifiedPost:
    """Enforce word count range: mechanical trim -> LLM retry -> flag violation."""
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
        logger.warning("[batch] %s VIOLATION: %s - flagged for review", post.label, violation)
    return post


def _generate_pack_lean(
    llm: LLMProvider,
    source: str,
    pack_number: int,
    state: BatchState,
    posts_per_source: int = 9,
    event_callback=None,
    llm_prep: LLMProvider | None = None,
) -> PackResult:
    """Lean mode: uses transpose() for batched generation (3 posts/call)."""
    logger.info("[batch] Generating lean pack %d (%d posts) via transpose...", pack_number, posts_per_source)

    posts_per_source = max(1, min(posts_per_source, 9))

    # Dissect source (separate call on prep model)
    dissection = dissect_source(llm_prep or llm, source, state, pack_num=pack_number)
    dissection = verify_opener_tests(dissection)
    state.source_dissections.append(dissection)
    mirrorable = dissection.get("mirrorable", True) and not dissection.get("skip_batch_a", False)

    if event_callback:
        event_callback(f"pack_{pack_number}_dissected", {
            "hook_mechanic": dissection.get("hook_mechanic_primary", "unknown"),
            "mirrorable": mirrorable,
            "lean": True,
        })

    posts: list[AmplifiedPost] = []
    prior_args: list[str] = []

    # Batch A: 1 transpose call → 3 mirrored posts
    if mirrorable:
        n_a = min(3, posts_per_source)
        a_posts = transpose(llm, source, dissection, mode="A", state=state,
                           prior_arguments=prior_args, post_count=n_a, pack_number=pack_number)

        if not a_posts:
            logger.warning("[batch] Transpose A failed — retrying with post_count=1")
            for i in range(n_a):
                retry = transpose(llm, source, dissection, mode="A", state=state,
                                  prior_arguments=prior_args, post_count=1, pack_number=pack_number)
                if retry:
                    a_posts.extend(retry)
                    prior_args.extend(p.argument_compressed for p in retry if p.argument_compressed)

        # Batch A forbidden-token check (Fix 10 Part B)
        forbidden_tokens = _extract_forbidden_tokens(dissection, source)
        for idx, post in enumerate(a_posts):
            leaks = _scan_batch_a_for_token_leaks(post, forbidden_tokens)
            if leaks:
                logger.info(
                    "[batch] Pack %d %s: forbidden source tokens leaked: %s — regenerating",
                    pack_number, post.label, leaks,
                )
                post.quality_flags["batch_a_source_token_leak"] = leaks
                regen_hint = (
                    "The previous draft copied SOURCE tokens "
                    f"({', '.join(leaks)}) into the opener. FORBIDDEN. "
                    "Replace with founder-specific anchors from FOUNDER INTERNALIZATION. "
                    "Preserve source's structural shape but use founder's own numbers/entities."
                )
                regen_posts = transpose(
                    llm, source, dissection, mode="A", state=state,
                    prior_arguments=prior_args, post_count=1, pack_number=pack_number,
                    regen_hint=regen_hint,
                )
                if regen_posts:
                    new_post = regen_posts[0]
                    new_post.label = post.label
                    new_post.regen_count = post.regen_count + 1
                    new_leaks = _scan_batch_a_for_token_leaks(new_post, forbidden_tokens)
                    if new_leaks:
                        new_post.quality_flags["batch_a_source_token_leak_unfixed"] = new_leaks
                    a_posts[idx] = new_post

        for post in a_posts:
            post = _enforce_word_count(post, state, llm=llm)
            posts.append(post)
            if post.argument_compressed:
                prior_args.append(post.argument_compressed)

        if event_callback:
            event_callback(f"pack_{pack_number}_a_transpose", {"count": len(a_posts)})
        n_b = max(0, posts_per_source - len(posts))
    else:
        n_b = posts_per_source

    # Batch B: 2 transpose calls of 3 posts each
    if n_b > 0:
        doors = select_entry_doors(n_b, state.entry_doors_used, pack_number)
        state.entry_doors_used[pack_number] = doors

        # First B batch (3 posts)
        batch_1_doors = doors[:3]
        b_posts_1 = transpose(llm, source, dissection, mode="B", state=state,
                             doors=batch_1_doors, prior_arguments=prior_args,
                             post_count=min(3, n_b), pack_number=pack_number)

        if not b_posts_1:
            logger.warning("[batch] Transpose B1 failed — retrying per-door")
            for door in batch_1_doors:
                retry = transpose(llm, source, dissection, mode="B", state=state,
                                  doors=[door], prior_arguments=prior_args,
                                  post_count=1, pack_number=pack_number)
                if retry:
                    b_posts_1.extend(retry)
                    prior_args.extend(p.argument_compressed for p in retry if p.argument_compressed)

        for post in b_posts_1:
            post = _enforce_word_count(post, state, llm=llm)
            posts.append(post)
            if post.argument_compressed:
                prior_args.append(post.argument_compressed)

        if event_callback:
            event_callback(f"pack_{pack_number}_b_transpose_1", {"count": len(b_posts_1)})

        # Second B batch if needed
        remaining = n_b - len(b_posts_1)
        if remaining > 0 and len(doors) > 3:
            batch_2_doors = doors[3:6]
            b_posts_2 = transpose(llm, source, dissection, mode="B", state=state,
                                 doors=batch_2_doors, prior_arguments=prior_args,
                                 post_count=min(3, remaining), pack_number=pack_number)

            if not b_posts_2:
                logger.warning("[batch] Transpose B2 failed — retrying per-door")
                for door in batch_2_doors:
                    retry = transpose(llm, source, dissection, mode="B", state=state,
                                      doors=[door], prior_arguments=prior_args,
                                      post_count=1, pack_number=pack_number)
                    if retry:
                        b_posts_2.extend(retry)
                        prior_args.extend(p.argument_compressed for p in retry if p.argument_compressed)

            for post in b_posts_2:
                post = _enforce_word_count(post, state, llm=llm)
                posts.append(post)
                if post.argument_compressed:
                    prior_args.append(post.argument_compressed)

            if event_callback:
                event_callback(f"pack_{pack_number}_b_transpose_2", {"count": len(b_posts_2)})

    # Fix labels to sequential numbering
    a_idx, b_idx = 0, 0
    for post in posts:
        if post.batch == "A":
            a_idx += 1
            post.label = f"A{a_idx}"
        else:
            b_idx += 1
            post.label = f"B{b_idx}"

    n_a_actual = len([p for p in posts if p.batch == "A"])
    n_b_actual = len([p for p in posts if p.batch == "B"])
    return PackResult(
        source_number=pack_number,
        source_post=source,
        dissection=dissection,
        mirrorable=mirrorable,
        posts=posts,
        batch_a_count=n_a_actual,
        batch_b_count=n_b_actual,
    )


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

    prior_args: list[str] = []

    if mirrorable:
        n_a = min(3, posts_per_source)
        logger.info("[batch] Pack %d: generating %d A posts via transpose...", pack_number, n_a)
        a_posts = transpose(llm, source, dissection, mode="A", state=state,
                           prior_arguments=prior_args, post_count=n_a, pack_number=pack_number)

        # Batch A forbidden-token check (Fix 10 Part B): scan each A opener for
        # source-specific tokens; regen once if leak found.
        forbidden_tokens = _extract_forbidden_tokens(dissection, source)
        for idx, post in enumerate(a_posts):
            leaks = _scan_batch_a_for_token_leaks(post, forbidden_tokens)
            if leaks:
                logger.info(
                    "[batch] Pack %d %s: forbidden source tokens leaked into opener: %s — regenerating",
                    pack_number, post.label, leaks,
                )
                post.quality_flags["batch_a_source_token_leak"] = leaks
                regen_hint = (
                    "The previous draft copied the SOURCE's specific tokens "
                    f"({', '.join(leaks)}) into the opener. These are FORBIDDEN. "
                    "Replace them with founder-specific anchors from FOUNDER INTERNALIZATION. "
                    "Preserve the source's structural shape (sentence count, beat order, mechanic family) "
                    "but use the founder's own numbers and entities."
                )
                regen_posts = transpose(
                    llm, source, dissection, mode="A", state=state,
                    prior_arguments=prior_args, post_count=1, pack_number=pack_number,
                    regen_hint=regen_hint,
                )
                if regen_posts:
                    new_post = regen_posts[0]
                    new_post.label = post.label
                    new_post.regen_count = post.regen_count + 1
                    new_leaks = _scan_batch_a_for_token_leaks(new_post, forbidden_tokens)
                    if new_leaks:
                        new_post.quality_flags["batch_a_source_token_leak_unfixed"] = new_leaks
                    a_posts[idx] = new_post

        for post in a_posts:
            post = _enforce_word_count(post, state, llm=llm)
            posts.append(post)
            if post.argument_compressed:
                prior_args.append(post.argument_compressed)
            if event_callback:
                event_callback(f"pack_{pack_number}_{post.label}", {"word_count": post.word_count})
        n_b = max(0, posts_per_source - len(a_posts))
    else:
        n_b = posts_per_source

    doors = select_entry_doors(n_b, state.entry_doors_used, pack_number)
    state.entry_doors_used[pack_number] = doors

    for batch_start in range(0, n_b, 3):
        batch_doors = doors[batch_start:batch_start + 3]
        batch_count = min(3, n_b - batch_start)
        logger.info("[batch] Pack %d: generating %d B posts (doors: %s)...", pack_number, batch_count, batch_doors)
        b_posts = transpose(llm, source, dissection, mode="B", state=state,
                           doors=batch_doors, prior_arguments=prior_args,
                           post_count=batch_count, pack_number=pack_number)
        for post in b_posts:
            post = _enforce_word_count(post, state, llm=llm)
            posts.append(post)
            if post.argument_compressed:
                prior_args.append(post.argument_compressed)
        if event_callback:
            event_callback(f"pack_{pack_number}_b_batch", {
                "doors": batch_doors, "count": len(b_posts),
            })

    # Fix B-label collision: each transpose() call labels its outputs
    # B1/B2/B3 starting from 1, so two calls produce duplicate labels.
    # Renumber sequentially across the whole pack (mirrors _generate_pack_lean).
    a_idx, b_idx = 0, 0
    for post in posts:
        if post.batch == "A":
            a_idx += 1
            post.label = f"A{a_idx}"
        else:
            b_idx += 1
            post.label = f"B{b_idx}"

    n_a_actual = len([p for p in posts if p.batch == "A"])
    n_b_actual = len([p for p in posts if p.batch == "B"])
    return PackResult(
        source_number=pack_number,
        source_post=source,
        dissection=dissection,
        mirrorable=mirrorable,
        posts=posts,
        batch_a_count=n_a_actual,
        batch_b_count=n_b_actual,
    )
