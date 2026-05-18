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
from .amplifier import TEMPLATE_REPOSITORY

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
    """v6: Dissect viral source via 02_dissect.txt.

    Now takes `anchor_inventory` + `inventory_summary` and outputs
    `source_fitness_check.routing_decision` which the orchestrator honors
    upstream of generation.
    """
    if getattr(state, "llm_router", None):
        llm = state.llm_router.for_task("dissect")
    template = load_prompt(PROMPTS_DIR / "source_dissect_hook.txt")

    # v6 placeholders: anchor_inventory + inventory_summary
    inv_full = state.anchor_inventory or {}
    inv_list = inv_full.get("anchor_inventory", []) or []
    inv_summary = inv_full.get("inventory_summary", {}) or {}

    # v6.1: feed the 13-template repository to the dissect prompt so it can
    # pick a hook_mechanic_primary + hook_sub_mechanic from a known catalog
    # AND select a batch_b_template_match. Compact view — drop verbose
    # description fields to keep prompt size bounded.
    repo_compact = [
        {
            "id": t.get("id"),
            "tier": t.get("tier"),
            "name": t.get("name"),
            "sub_mechanics": t.get("sub_mechanics", []),
            "narrative_engine": t.get("narrative_engine"),
            "closing_move": t.get("closing_move"),
            "parameter_list": t.get("parameter_list", []),
            "mirror_requires": t.get("mirror_requires", []),
            "strip_test_template": t.get("strip_test_template"),
            "example_openings": (t.get("example_openings") or [])[:2],
        }
        for t in (TEMPLATE_REPOSITORY or [])
    ]

    prompt = fill_prompt(
        template,
        source_post=source,
        platform=state.platform,
        anchor_inventory=json.dumps(inv_list, ensure_ascii=False)[:8000] or "(no inventory)",
        inventory_summary=json.dumps(inv_summary, ensure_ascii=False)[:2000] or "{}",
        template_repository=json.dumps(repo_compact, ensure_ascii=False)[:8000] or "[]",
    )

    import time as _t
    _start = _t.time()
    response = llm.generate(prompt, temperature=0.2, max_tokens=3000)
    _dur = int((_t.time() - _start) * 1000)
    result = parse_llm_json(response)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage=f"pack_{pack_num}_dissect",
            template="02_dissect.txt",
            prompt=prompt,
            response=response,
            temperature=0.2,
            max_tokens=3000,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
            llm=llm,
        )

    if not isinstance(result, dict):
        # On parse failure, default to the safe "no batch A" path.
        state.routing_decision = "skip_batch_a_route_all_to_b"
        return {
            "narrative_arc": "unknown",
            "mirrorable": True,
            "skip_batch_a": True,
            "source_fitness_check": {
                "routing_decision": "skip_batch_a_route_all_to_b",
                "fitness_explanation": "dissect parse failed — defaulting to all-B for safety",
            },
        }

    # Surface a legacy alias so old callers looking up "hook_mechanic_primary"
    # AND new ones referencing same key both work.
    if "hook_mechanic_primary" not in result and "hook_mechanic" in result:
        result["hook_mechanic_primary"] = result["hook_mechanic"]

    # v6.1: parse source_fitness_check.
    fitness = result.get("source_fitness_check") or {}
    advisory_routing = fitness.get("routing_decision", "generate_4_batch_a_5_batch_b")

    # USER OVERRIDE: always force 4A+5B. The user wants both batches every
    # time. v6.1's conservative routing (skip Batch A when sub-mechanic
    # mismatches) is downgraded to advisory — the validator + regen loop
    # will still try to mirror, and posts that can't will be flagged for
    # the user to inspect. Posts that fundamentally can't sub-mechanic-mirror
    # may not hit Parameter 1 = 10.0 — that's the data limit, not a code bug.
    routing = "generate_4_batch_a_5_batch_b"
    if advisory_routing != routing:
        logger.warning(
            "[batch] force_4a_5b override: dissect said %s but generating 4A+5B anyway "
            "(required_sub_mechanic=%s, anchor_matches=%s, mirror_feasible=%s). "
            "Batch A posts may not achieve Parameter 1 = 10.0 if no anchor matches the sub-mechanic.",
            advisory_routing,
            fitness.get("required_sub_mechanic", "?"),
            fitness.get("matching_sub_mechanic_count", "?"),
            fitness.get("mirror_feasible", "?"),
        )
        # Flag for regen_loop to skip mirror-integrity early reject.
        state.force_4a_5b_applied = True
    else:
        state.force_4a_5b_applied = False
    state.routing_decision = routing
    # v6.1 log line matches README §"Verifying v6.1 is working" verbatim shape.
    logger.info(
        "[batch] Pack %d dissect routing: %s "
        "(fitness=%s, required_sub_mechanic=%s, sub_mechanic_matches=%s, "
        "mirror_feasible=%s, usable_anchors=%s)",
        pack_num,
        routing,
        fitness.get("fitness_score", "?"),
        fitness.get("required_sub_mechanic", "?"),
        fitness.get("matching_sub_mechanic_count", fitness.get("total_usable_count", "?")),
        fitness.get("mirror_feasible", "?"),
        fitness.get("total_usable_count", "?"),
    )
    return result


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


# ============================================================================
# v5 sequential generation — 03_generate.txt
# ============================================================================

def _build_anchors_remaining(voice_load: dict) -> list[str]:
    """Initial anchors list = key_moments_inventory + signature_scenes from voice_load.

    These accumulate as "used" once a post claims one in its declaration.
    """
    moments = voice_load.get("key_moments_inventory", []) or []
    scenes = voice_load.get("signature_scenes", []) or []
    cast = voice_load.get("recurring_cast", []) or []
    out: list[str] = []
    for x in moments + scenes + cast:
        if isinstance(x, str) and x.strip():
            out.append(x.strip())
        elif isinstance(x, dict):
            label = x.get("label") or x.get("title") or x.get("name") or ""
            if label:
                out.append(label.strip())
    return out


def _compress_prior_posts_v6(prior_posts: list[dict]) -> str:
    """Render prior_posts for the v6 03_generate.txt prompt.

    v6 schema requires: label, argument_compressed, opener_text,
    body_paragraph_2, closer_text, anchor_used, tier, closer_mechanic,
    entry_door, structural_skeleton, surprise_quotient.

    Each field is capped to keep total prior_posts block under ~3KB even
    on post 9 of the pack.
    """
    if not prior_posts:
        return "(none — this is the first post in the pack)"
    lines = []
    for p in prior_posts:
        compact = {
            "label": p.get("label", ""),
            "argument_compressed": (p.get("argument_compressed") or "")[:300],
            "opener_text": (p.get("opener_text") or "")[:300],
            "body_paragraph_2": (p.get("body_paragraph_2") or "")[:300],
            "closer_text": (p.get("closer_text") or "")[:300],
            "anchor_used": p.get("anchor_used") or "",
            "tier": p.get("tier") or "",
            "closer_mechanic": p.get("closer_mechanic") or "",
            "entry_door": p.get("entry_door") or "",
            "structural_skeleton": (p.get("structural_skeleton") or {}),
            "surprise_quotient": (p.get("surprise_quotient") or {}),
        }
        lines.append(json.dumps(compact, ensure_ascii=False))
    return "\n".join(lines)


def _extract_body_paragraph_2_and_closer(text: str) -> tuple[str, str]:
    """Pull the second body paragraph + the final paragraph (closer) from a post."""
    if not text:
        return "", ""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return "", ""
    body_p2 = paragraphs[2] if len(paragraphs) >= 3 else ""
    closer = paragraphs[-1] if len(paragraphs) >= 2 else ""
    return body_p2, closer


def _generate_one_post(
    llm: LLMProvider,
    source: str,
    dissection: dict,
    voice_load: dict,
    post_index: int,
    post_label: str,
    post_type: str,
    post_count: int,
    prior_posts: list[dict],
    state: BatchState,
    pack_num: int = 0,
    regen_attempt: int = 0,
    failed_parameters: list[str] | None = None,
    explicit_avoid: list[str] | None = None,
    required_sub_mechanic: str = "",
    anchor_to_use: str = "",
    regenerate_with_mechanic: str = "",
    fallback_strategy: str = "",
    prior_attempt_text: str = "",
) -> AmplifiedPost | None:
    """v6.1: Generate ONE post via 03_generate.txt with consumable inventory.

    Reads from `state.inventory` (PackInventoryState) for anchors_remaining,
    anchors_used_in_pack, voice_marker_budget_remaining, voice_markers_used_in_pack.

    On `regen_attempt > 0`, also includes:
      - failed_parameters / explicit_avoid (what the prior attempt did wrong)
      - required_sub_mechanic / anchor_to_use / regenerate_with_mechanic
        (the validator's specific guidance for what to do this time)
      - fallback_strategy / prior_attempt_text

    All regen guidance is surfaced via synthetic prior_posts entries so the v6
    03_generate.txt prompt (unchanged in v6.1) can read it through its existing
    prior_posts placeholder.

    Returns None on parse failure.
    """
    if getattr(state, "llm_router", None):
        try:
            llm = state.llm_router.for_task("generate")
        except Exception:
            task = "generate_a" if post_type == "A" else "generate_b"
            llm = state.llm_router.for_task(task)

    template = load_prompt(PROMPTS_DIR / "transpose.txt")

    inv = state.inventory
    anchors_remaining_list = inv.anchors_available if inv else []
    anchors_used_in_pack = inv.anchors_used_in_pack if inv else []
    voice_markers_used_in_pack = inv.voice_markers_used_in_pack if inv else []
    voice_marker_budget_remaining = inv.voice_marker_budget_remaining() if inv else []

    # Cap dissection + voice_load JSON to keep prompt size bounded.
    dissection_str = json.dumps(dissection, ensure_ascii=False)[:6000]
    voice_load_str = json.dumps(voice_load, ensure_ascii=False)[:6000]

    # Build the v6 forbidden_templates block (object array — keep as JSON).
    forbidden_templates = dissection.get("forbidden_templates", []) or []
    forbidden_phrases = dissection.get("forbidden_phrases", []) or []

    forbidden_phrases_str = (
        "\n".join(f"- {p}" for p in forbidden_phrases)
        if forbidden_phrases else "(none extracted from source)"
    )
    forbidden_templates_str = (
        json.dumps(forbidden_templates, ensure_ascii=False)
        if forbidden_templates else "(none extracted from source)"
    )

    # If this is a regen, append regen-specific guidance to the prior_posts
    # block so the model sees the prior attempt + what failed + what to avoid.
    prior_posts_for_prompt = list(prior_posts)
    if regen_attempt > 0:
        # Synthesize the prior-attempt-context entry. The v6.1 validator gives
        # us 4 levers (required_sub_mechanic, anchor_to_use, regenerate_with_mechanic,
        # fallback_strategy) and we surface ALL of them so the model can pick
        # the right anchor + mechanic this time.
        regen_context = {
            "failed_parameters": failed_parameters or [],
            "explicit_avoid": explicit_avoid or [],
            "required_sub_mechanic": required_sub_mechanic or "",
            "anchor_to_use": anchor_to_use or "",
            "regenerate_with_mechanic": regenerate_with_mechanic or "",
            "fallback_strategy": fallback_strategy or "",
            "instruction": (
                f"REGEN ATTEMPT {regen_attempt}/3. Previous attempt failed on "
                f"{failed_parameters or 'unknown parameters'}. "
                + (f"Required sub-mechanic THIS time: {required_sub_mechanic}. " if required_sub_mechanic else "")
                + (f"Use anchor: {anchor_to_use}. " if anchor_to_use else "")
                + (f"Regenerate with mechanic: {regenerate_with_mechanic}. " if regenerate_with_mechanic else "")
                + (f"Fallback strategy: {fallback_strategy}. " if fallback_strategy else "")
            ),
        }
        prior_posts_for_prompt.append({
            "label": f"PRIOR_ATTEMPT_{post_label}",
            "argument_compressed": "Your previous attempt that failed validation — see regen_context below",
            "opener_text": (prior_attempt_text or "")[:500],
            "body_paragraph_2": "",
            "closer_text": "",
            "anchor_used": "",
            "tier": "",
            "closer_mechanic": "",
            "entry_door": "",
            "structural_skeleton": regen_context,
            "surprise_quotient": {"explicit_avoid": explicit_avoid or []},
        })

    wc_lo, wc_hi = min(state.word_count_range), max(state.word_count_range)

    # Mode rules for transpose.txt (inline — Batch A mirrors, Batch B diverges)
    mode_rules_str = (
        f"This is a Batch {post_type} post. "
        + ("Mirror the source hook's sentence shape (beats 1-2 only). Replace every concrete noun with the founder's world. Body MUST diverge from other A variants."
           if post_type == "A"
           else "Same psychological move as source, fully different surface. Use a DIFFERENT entry door from prior posts.")
    )

    prompt = fill_prompt(
        template,
        post_index=str(post_index),
        post_label=post_label,
        post_type=post_type,
        post_count="1",
        regen_attempt=str(regen_attempt),
        source_post=source,
        dissection=dissection_str,
        platform=state.platform,
        voice_load=voice_load_str,
        calibration_paragraph=voice_load.get("calibration_paragraph", "") or state.calibration_paragraph or "(no calibration available)",
        anchors_used_in_pack=json.dumps(anchors_used_in_pack, ensure_ascii=False)[:3000] or "(none yet)",
        anchors_remaining=json.dumps(anchors_remaining_list, ensure_ascii=False)[:6000] or "(no anchors available)",
        voice_markers_used_in_pack=json.dumps(voice_markers_used_in_pack, ensure_ascii=False) or "(none yet)",
        voice_marker_budget_remaining=json.dumps(voice_marker_budget_remaining, ensure_ascii=False) or "(no markers in budget)",
        prior_posts=_compress_prior_posts_v6(prior_posts_for_prompt),
        forbidden_phrases=forbidden_phrases_str,
        forbidden_templates=forbidden_templates_str,
        word_count_range=f"{wc_lo}-{wc_hi} words",
        # transpose.txt placeholders (fill_prompt ignores extras for old prompt)
        mode="declaring",
        mode_rules=mode_rules_str,
        internalization=voice_load_str,
        voice_markers="\n".join(f"- {m}" for m in state.voice_markers),
        marker_rates=json.dumps(state.marker_rates or {}, ensure_ascii=False),
        personality_card=state.personality_card[:3000],
        formatting_habits=json.dumps(state.formatting_habits or {}, ensure_ascii=False),
        web_search_facts=json.dumps(state.web_search_context or {}, ensure_ascii=False)[:4000],
        prior_arguments="\n".join(
            f"- {p.get('argument_compressed', '')}" for p in prior_posts_for_prompt
            if p.get("argument_compressed")
        ) or "(none yet — this is the first post)",
        events_used=json.dumps(list(state.events_used_global), ensure_ascii=False) if state.events_used_global else "(none yet)",
        stories_used=json.dumps(list(state.stories_used_global), ensure_ascii=False) if state.stories_used_global else "(none yet)",
    )

    import time as _t
    _start = _t.time()
    try:
        response = llm.generate(prompt, temperature=0.5, max_tokens=6000)
    except Exception as e:
        logger.warning("[generate] %s API error: %s", post_label, e)
        return None
    _dur = int((_t.time() - _start) * 1000)
    result = parse_llm_json(response)

    # transpose.txt wraps output in {"posts": [...]} — unwrap to flat dict.
    if isinstance(result, dict) and "posts" in result and isinstance(result["posts"], list):
        if result["posts"]:
            result = result["posts"][0]
        else:
            result = {}

    if state.tracer:
        state.tracer.trace_llm_call(
            stage=f"pack_{pack_num}_generate_{post_label}",
            template="03_generate.txt",
            prompt=prompt,
            response=response,
            temperature=0.5,
            max_tokens=6000,
            duration_ms=_dur,
            thinking=getattr(llm, 'last_thinking', ''),
            llm=llm,
            metadata={
                "label": post_label,
                "type": post_type,
                "prior_count": len(prior_posts),
                "regen_attempt": regen_attempt,
                "anchors_remaining": len(anchors_remaining_list),
            },
        )

    if not isinstance(result, dict) or not result.get("text"):
        logger.warning("[generate] %s parse failed or empty text", post_label)
        return None

    # v6 output schema: pre_commit{}, text, mode, events_used, stories_used,
    # voice_markers_used (list of marker_ids), anchor_consumed_id, word_count,
    # self_scores{}.
    pre_commit = result.get("pre_commit") or result.get("declaration") or {}
    if not isinstance(pre_commit, dict):
        pre_commit = {}
    self_scores = result.get("self_scores") or {}
    if not isinstance(self_scores, dict):
        self_scores = {}

    text = result.get("text", "").strip()
    paragraphs = text.split("\n\n")

    anchor_consumed_id = (
        result.get("anchor_consumed_id")
        or (pre_commit.get("anchor_consumed") or {}).get("anchor_id")
        or pre_commit.get("authority_anchor", "")
        or ""
    )

    # voice_markers_used in v6 is a list of marker_ids (strings). Older v5
    # results returned a list of marker_text strings — accept either.
    voice_markers_used = result.get("voice_markers_used", []) or []
    if not isinstance(voice_markers_used, list):
        voice_markers_used = []

    post = AmplifiedPost(
        label=post_label,
        batch=post_type,
        entry_door=pre_commit.get("entry_door") or ("mirrored" if post_type == "A" else pre_commit.get("mechanic", "unknown")),
        mode=result.get("mode", pre_commit.get("mode", "declaring")),
        text=text,
        word_count=int(result.get("word_count") or len(text.split())),
        original_opening=paragraphs[0] if paragraphs else "",
        final_opening=paragraphs[0] if paragraphs else "",
        mechanic=pre_commit.get("mechanic") or "",
        argument_compressed=pre_commit.get("argument_compressed", ""),
        events_used=result.get("events_used", []) or [],
        stories_used=result.get("stories_used", []) or [],
        closer_mechanic=pre_commit.get("closer_mechanic", ""),
        authority_anchor=(pre_commit.get("anchor_consumed") or {}).get("anchor_id", "") or pre_commit.get("authority_anchor", "") or anchor_consumed_id,
        body_format=pre_commit.get("body_format", ""),
        body_divergence_check=pre_commit.get("body_divergence_check", []) or [],
        strip_test_residue=pre_commit.get("strip_test_residue", ""),
        pre_commit=pre_commit,
        self_scores=self_scores,
        anchor_consumed_id=anchor_consumed_id,
        surprise_quotient=pre_commit.get("surprise_quotient") or {},
        regen_count=regen_attempt,
    )

    # Stash voice_markers_used on the post object via opener_variants slot
    # (re-purposed; the regen loop reads this back via post.pre_commit too).
    post.pre_commit["_voice_markers_used_runtime"] = voice_markers_used

    # Consume inventory.
    if inv is not None:
        if anchor_consumed_id:
            inv.consume_anchor(anchor_consumed_id)
        for marker_id in voice_markers_used:
            if isinstance(marker_id, str):
                inv.consume_voice_marker(marker_id)
            elif isinstance(marker_id, dict):
                inv.consume_voice_marker(marker_id.get("marker_id", ""))

    # Global tracking (events / stories) — unchanged from v5.
    state.events_used_global.update(post.events_used)
    state.stories_used_global.update(post.stories_used)
    for s in post.stories_used:
        if s:
            state.story_usage_counter[s] = state.story_usage_counter.get(s, 0) + 1

    self_score_below = self_scores.get("self_score_below_threshold", False)
    lowest = self_scores.get("lowest_parameter_score", "?")
    logger.info(
        "[generate] %s done: wc=%d self_lowest=%s self_below_threshold=%s anchor=%s",
        post_label, post.word_count, lowest, self_score_below, anchor_consumed_id,
    )

    return post


_ROUTING_TO_LABELS = {
    "generate_4_batch_a_5_batch_b": [("A", 1), ("A", 2), ("A", 3), ("A", 4),
                                     ("B", 1), ("B", 2), ("B", 3), ("B", 4), ("B", 5)],
    "generate_3_batch_a_6_batch_b": [("A", 1), ("A", 2), ("A", 3),
                                     ("B", 1), ("B", 2), ("B", 3), ("B", 4), ("B", 5), ("B", 6)],
    "generate_2_batch_a_7_batch_b": [("A", 1), ("A", 2),
                                     ("B", 1), ("B", 2), ("B", 3), ("B", 4),
                                     ("B", 5), ("B", 6), ("B", 7)],
    "skip_batch_a_route_all_to_b": [("B", i + 1) for i in range(9)],
}


def generate_pack_sequential(
    llm: LLMProvider,
    source: str,
    dissection: dict,
    state: BatchState,
    pack_num: int = 0,
    event_callback=None,
    posts_per_source: int = 9,
) -> list[AmplifiedPost]:
    """v6: Generate posts sequentially honoring `state.routing_decision`.

    Routing options (from 02_dissect.source_fitness_check.routing_decision):
      - generate_4_batch_a_5_batch_b: normal 9-post pack (4A+5B)
      - generate_3_batch_a_6_batch_b: moderate fit (3A+6B)
      - generate_2_batch_a_7_batch_b: low-moderate fit (2A+7B)
      - skip_batch_a_route_all_to_b: low fit, all 9 to Batch B
      - reject_source_insufficient_fit: caller should skip this source entirely

    `posts_per_source` (1-9, default 9) caps the total number of posts produced
    from the routing-determined labels list. posts_per_source=1 → 1 post,
    posts_per_source=3 → 3 posts, etc. When < 9 and routing produces an A+B mix,
    Batch A labels are taken first.
    """
    voice_load_data = state.voice_load or state.founder_internalization or {}
    routing = state.routing_decision or "generate_4_batch_a_5_batch_b"

    if routing == "reject_source_insufficient_fit":
        logger.warning(
            "[generate] Pack %d: routing=reject_source_insufficient_fit — skipping generation",
            pack_num,
        )
        return []

    # Legacy fallback when dissection didn't produce a routing decision
    # (e.g., parse failure before v6 took effect): respect skip_batch_a flag.
    if routing not in _ROUTING_TO_LABELS:
        if dissection.get("skip_batch_a") or not dissection.get("mirrorable", True):
            routing = "skip_batch_a_route_all_to_b"
        else:
            routing = "generate_4_batch_a_5_batch_b"

    labels = _ROUTING_TO_LABELS[routing]

    # User cap: posts_per_source (1-9, default 9) limits the total number of
    # posts produced. When < 9, we slice from the front of the labels list,
    # which preserves A-first ordering — so posts_per_source=1 gives just A1,
    # posts_per_source=4 gives A1..A4, posts_per_source=5 gives A1..A4+B1, etc.
    capped = max(1, min(int(posts_per_source or 9), len(labels)))
    if capped < len(labels):
        logger.info(
            "[generate] Pack %d: posts_per_source=%d caps routing %s from %d to %d posts",
            pack_num, capped, routing, len(labels), capped,
        )
        labels = labels[:capped]

    logger.info("[generate] Pack %d: routing=%s → %d posts (%s)",
                pack_num, routing, len(labels),
                ",".join(f"{b}{n}" for b, n in labels))

    prior_posts: list[dict] = []
    wc_range = state.word_count_range
    inv = state.inventory  # may be None when caller didn't init; helpers defend

    pack: list[AmplifiedPost] = []
    for i, (batch, n) in enumerate(labels, start=1):
        label = f"{batch}{n}"
        anchors_left = len(inv.anchors_available) if inv else 0
        logger.info(
            "[generate] %s start: post_type=%s prior_posts=%d anchors_remaining=%d",
            label, batch, len(prior_posts), anchors_left,
        )
        post = _generate_one_post(
            llm, source, dissection, voice_load_data,
            post_index=i, post_label=label, post_type=batch, post_count=1,
            prior_posts=prior_posts,
            state=state, pack_num=pack_num,
            regen_attempt=0,
        )
        if post is None:
            # Single retry on parse failure (no model change).
            logger.warning("[generate] %s: retrying once after parse failure", label)
            post = _generate_one_post(
                llm, source, dissection, voice_load_data,
                post_index=i, post_label=label, post_type=batch, post_count=1,
                prior_posts=prior_posts,
                state=state, pack_num=pack_num,
                regen_attempt=0,
            )
        if post is None:
            logger.error("[generate] %s: failed twice — skipping post", label)
            continue

        post = _enforce_word_count(post, state, llm=llm)

        # v6.1: NO inline body-diff regen here. Per "deterministic API calls only"
        # directive — the pack-level validator is the sole authority on
        # cross-variant similarity. Previous Phase 2.5 inline Jaccard heuristic
        # produced false-positive regens (common phrasing flagged as overlap).
        pack.append(post)

        # Record prior_posts entry with v6 richer schema for the NEXT call.
        body_p2, closer_text = _extract_body_paragraph_2_and_closer(post.text)
        prior_posts.append({
            "label": label,
            "argument_compressed": post.argument_compressed,
            "opener_text": (post.text.split("\n\n")[0] if post.text else ""),
            "body_paragraph_2": body_p2,
            "closer_text": closer_text,
            "anchor_used": post.authority_anchor or post.anchor_consumed_id,
            "tier": (post.pre_commit.get("anchor_consumed") or {}).get("tier", ""),
            "closer_mechanic": post.closer_mechanic,
            "entry_door": post.entry_door,
            "structural_skeleton": post.pre_commit.get("structural_skeleton") or {},
            "surprise_quotient": post.surprise_quotient or {},
        })

        if event_callback:
            event_callback(f"pack_{pack_num}_{label}", {
                "word_count": post.word_count,
                "argument": (post.argument_compressed or "")[:80],
                "anchor": post.authority_anchor or post.anchor_consumed_id,
                "closer": post.closer_mechanic,
                "entry_door": post.entry_door,
                "self_lowest_param": (post.self_scores or {}).get("lowest_parameter_score"),
            })

    # Bug B: assert labels unique within pack.
    seen_labels = {p.label for p in pack}
    assert len(seen_labels) == len(pack), (
        f"label collision in generated pack: {[p.label for p in pack]}"
    )

    return pack


# ============================================================================
# v4 transpose — kept as a thin shim for the legacy convergence regen path.
# Internally delegates to _generate_one_post() so old callers keep working
# without resurrecting the deprecated transpose.txt prompt.
# ============================================================================

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
    """v5 shim: legacy `transpose()` callers (notably the convergence regen
    path in session.py) get a one-shot call into `_generate_one_post()`.

    The v5 prompt is `03_generate.txt` — there's no batched mode; we just loop.
    `diversity_override` / `regen_hint` are appended as synthetic entries in
    `prior_posts` so the model is told what to avoid without growing the
    prompt schema.
    """
    voice_load_data = state.voice_load or state.founder_internalization or {}

    # Build synthetic prior_posts from the regen hints — the v5 prompt only
    # speaks the `prior_posts` shape, so we encode regen guidance there.
    prior_posts: list[dict] = []
    for arg in (prior_arguments or []):
        prior_posts.append({
            "label": "prev",
            "argument_compressed": arg,
            "opener_text": "",
            "anchor_used": "",
            "closer_mechanic": "",
            "entry_door": "",
        })
    if diversity_override:
        prior_posts.append({
            "label": "FORCED_ANGLE",
            "argument_compressed": f"FORCED ANGLE — your post MUST argue: {diversity_override}",
            "opener_text": "",
            "anchor_used": "",
            "closer_mechanic": "",
            "entry_door": "",
        })
    if regen_hint:
        prior_posts.append({
            "label": "REGEN_HINT",
            "argument_compressed": regen_hint,
            "opener_text": "",
            "anchor_used": "",
            "closer_mechanic": "",
            "entry_door": "",
        })
    if mechanic_override:
        prior_posts.append({
            "label": "AVOID_MECHANIC",
            "argument_compressed": f"Do NOT use opener mechanic: {mechanic_override}",
            "opener_text": "",
            "anchor_used": "",
            "closer_mechanic": "",
            "entry_door": "",
        })

    posts: list[AmplifiedPost] = []
    for i in range(post_count):
        label = f"{'A' if mode == 'A' else 'B'}{i + 1}"
        post_type = mode if mode in ("A", "B") else "B"
        forced_door = (doors[i] if (doors and i < len(doors)) else None)
        # v6 signature: no more anchors_remaining / forbidden_phrases /
        # word_count_range params — _generate_one_post pulls those from
        # state.inventory + state directly.
        post = _generate_one_post(
            llm, source, dissection, voice_load_data,
            post_index=i + 1, post_label=label, post_type=post_type,
            post_count=post_count, prior_posts=prior_posts,
            state=state, pack_num=pack_number,
            regen_attempt=0,
        )
        if post is None:
            continue
        # If caller insisted on a specific door for Batch B, override what the
        # model picked. Sequential generation usually picks correctly but
        # legacy callers pass an explicit door list.
        if forced_door and post_type == "B":
            post.entry_door = forced_door
        prior_posts.append({
            "label": label,
            "argument_compressed": post.argument_compressed,
            "opener_text": (post.text.split("\n\n")[0] if post.text else ""),
            "anchor_used": post.authority_anchor or post.anchor_consumed_id,
            "closer_mechanic": post.closer_mechanic,
            "entry_door": post.entry_door,
        })
        posts.append(post)

    logger.info("[transpose] (v6 shim) mode=%s produced %d/%d posts", mode, len(posts), post_count)
    return posts


def _llm_trim_post(
    llm: LLMProvider,
    post: AmplifiedPost,
    state: BatchState,
    strict: bool = False,
) -> AmplifiedPost:
    """Use LLM to trim a post that mechanical trimming couldn't fix.

    When `strict=True`, the prompt is harsher and the target shifts toward the
    lower bound (forces the model to cut more aggressively rather than land near
    the ceiling). Called as the second attempt after a soft trim overshoots.
    """
    if getattr(state, "llm_router", None):
        llm = state.llm_router.for_task("word_count_trim")
    _lo, _hi = state.word_count_range
    lo, hi = min(_lo, _hi), max(_lo, _hi)
    target = (lo + hi) // 2 if not strict else lo + (hi - lo) // 4
    stage_label = "word_count_trim_strict" if strict else "word_count_trim"
    if strict:
        prompt = f"""STRICT TRIM. This LinkedIn post is {post.word_count} words. It MUST come down to at most {hi} words. Prior trim attempt overshot — be MORE aggressive this time.

Rules:
- Keep ONLY the opening paragraph (first 1-2 sentences) and the closing line.
- DELETE entire middle paragraphs. Pick the 2-3 strongest middle paragraphs and KEEP THOSE. Cut everything else.
- If still over {hi}: cut filler phrases inside the surviving paragraphs.
- Do NOT add new content. ONLY remove.
- Aim for around {target} words; ABSOLUTE HARD CAP is {hi}.

Return ONLY the trimmed post text. No JSON, no explanation, no preamble."""
    else:
        prompt = f"""This LinkedIn post is {post.word_count} words. It MUST be trimmed to EXACTLY {target} words (hard limit: {lo}-{hi}).

Cut aggressively:
- Keep opening paragraph (first 1-2 sentences) exactly as-is
- Keep closing line exactly as-is
- DELETE the weakest middle paragraph entirely
- If still over {hi} words, shorten remaining middle paragraphs by cutting redundant phrases
- Do NOT add new content. Only remove.

Return ONLY the trimmed post text. No JSON, no explanation, no preamble."""
    prompt = prompt + f"\n\n---\n\n{post.text}"

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
        logger.info("[batch] LLM-trimmed%s %s from %d to %d words",
                    " (strict)" if strict else "", post.label, old_wc, new_wc)
    else:
        # Only accept the trimmed text if it's strictly better (closer to band).
        # Otherwise keep the original — caller will escalate to hard truncation.
        was_over = post.word_count > hi
        is_better = abs(new_wc - hi) < abs(post.word_count - hi) and new_wc < post.word_count
        if was_over and is_better and new_wc < post.word_count:
            old_wc = post.word_count
            post.text = trimmed
            post.word_count = new_wc
            logger.info("[batch] LLM-trimmed%s %s from %d to %d words (still over, but closer)",
                        " (strict)" if strict else "", post.label, old_wc, new_wc)
        else:
            logger.warning("[batch] LLM trim%s for %s produced %d words (wanted %d-%d), keeping prior",
                           " (strict)" if strict else "", post.label, new_wc, lo, hi)

    if state.tracer:
        state.tracer.trace_llm_call(
            stage=f"{stage_label}_{post.label}",
            template="(inline word-count trim)",
            prompt=prompt,
            response=response,
            temperature=0.2,
            max_tokens=max_tok,
            duration_ms=_dur,
            thinking="",
            llm=llm,
            metadata={"original_wc": post.word_count, "target": f"{lo}-{hi}", "strict": strict},
        )

    return post


def _hard_truncate_to_word_count(post: AmplifiedPost, hi: int) -> AmplifiedPost:
    """Last-resort sentence-aware truncation to enforce the upper band cap.

    Walks paragraphs left-to-right keeping the opener intact, accumulates
    sentences from the body until adding the next would exceed `hi`, then
    attempts to keep the closing line so the post still has a closer. Never
    splits a sentence mid-word.
    """
    import re
    paragraphs = post.text.strip().split("\n\n")
    if not paragraphs:
        return post

    opener = paragraphs[0]
    closer = paragraphs[-1] if len(paragraphs) > 1 else ""
    middle = paragraphs[1:-1] if len(paragraphs) > 2 else []

    opener_wc = len(opener.split())
    closer_wc = len(closer.split()) if closer else 0
    budget_for_middle = max(0, hi - opener_wc - closer_wc)

    kept_middle: list[str] = []
    used = 0
    for para in middle:
        # Sentence-level packing within each paragraph.
        sentences = re.split(r"(?<=[.!?])\s+", para.strip())
        kept_sents: list[str] = []
        for sent in sentences:
            sent_wc = len(sent.split())
            if used + sent_wc <= budget_for_middle:
                kept_sents.append(sent)
                used += sent_wc
            else:
                break
        if kept_sents:
            kept_middle.append(" ".join(kept_sents))
        if used >= budget_for_middle:
            break

    parts = [opener] + kept_middle
    if closer and closer != opener:
        parts.append(closer)
    new_text = "\n\n".join(parts)
    new_wc = len(new_text.split())
    logger.warning(
        "[batch] %s hard-truncated from %d to %d words (band cap %d) — last-resort sentence-aware cut",
        post.label, post.word_count, new_wc, hi,
    )
    post.text = new_text
    post.word_count = new_wc
    return post


def _enforce_word_count(post: AmplifiedPost, state: BatchState, llm: LLMProvider | None = None) -> AmplifiedPost:
    """v6.1: NO trim ladder, NO hard truncation. Per "deterministic API calls
    only" directive — the pack-level LLM validator judges whether word-count
    deviation is meaningful for THIS post, not a fixed band heuristic.

    A 7-word miss (e.g. 130 vs band 137-253) often isn't a quality problem;
    forcing an LLM trim there is wasted cost. The validator can read each
    post in context and decide whether to regen on length grounds.

    We do ONE cheap mechanical step: if the post has more than 3 paragraphs
    AND is over band, drop the second-to-last paragraph. This is a structural
    repair (not a heuristic gate) for the case where the generator clearly
    appended a redundant beat. If still over-band, we accept and move on.
    """
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
            logger.info("[batch] %s: mechanical-trimmed (drop weakest middle paragraph) %d → %d words",
                        post.label, wc, post.word_count)

    # Record current state for the validator to read. No further trimming,
    # no truncation. The validator's per_post_validation will surface
    # length-related concerns if any.
    if not (lo <= post.word_count <= hi):
        residual = f"word_count: {post.word_count} (band {lo}-{hi}, accepted; validator may regen)"
        post.violations.append(residual)
        logger.info("[batch] %s: word_count %d outside band [%d,%d] — passing to validator",
                    post.label, post.word_count, lo, hi)
    return post
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
    """v5: Lean mode now identical to default — both use sequential generation."""
    return generate_pack(
        llm, source, pack_number, state,
        posts_per_source=posts_per_source,
        event_callback=event_callback,
        llm_prep=llm_prep,
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
    """v5: Generate 9 posts for one source via sequential per-post generation.

    Order: A1→A2→A3→A4→B1→B2→B3→B4→B5. Each call sees prior posts so it
    can diverge. If dissection.skip_batch_a is True (opener fails strip test),
    routes all 9 to B labels.
    """
    logger.info("[batch] Generating pack %d (v5 sequential)...", pack_number)

    dissection = dissect_source(llm_prep or llm, source, state, pack_num=pack_number)
    dissection = verify_opener_tests(dissection)
    state.source_dissections.append(dissection)
    mirrorable = dissection.get("mirrorable", True) and not dissection.get("skip_batch_a", False)

    if event_callback:
        event_callback(f"pack_{pack_number}_dissected", {
            "hook_mechanic": dissection.get("hook_mechanic_primary", "unknown"),
            "mirrorable": mirrorable,
        })

    posts = generate_pack_sequential(
        llm, source, dissection, state,
        pack_num=pack_number, event_callback=event_callback,
        posts_per_source=posts_per_source,
    )

    # Stamp Batch A forbidden-token leaks as quality_flags for downstream
    # awareness, but don't regenerate here — validate_pack will catch real
    # convergence/leak problems at the end.
    forbidden_tokens = _extract_forbidden_tokens(dissection, source)
    for post in posts:
        if post.batch == "A":
            leaks = _scan_batch_a_for_token_leaks(post, forbidden_tokens)
            if leaks:
                post.quality_flags["batch_a_source_token_leak"] = leaks

    n_a_actual = sum(1 for p in posts if p.batch == "A")
    n_b_actual = sum(1 for p in posts if p.batch == "B")
    return PackResult(
        source_number=pack_number,
        source_post=source,
        dissection=dissection,
        mirrorable=mirrorable,
        posts=posts,
        batch_a_count=n_a_actual,
        batch_b_count=n_b_actual,
    )
