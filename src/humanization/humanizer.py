"""Apply style rules from the knowledge graph to humanize generated posts."""

from __future__ import annotations

import logging
from pathlib import Path

from ..llm.base import LLMProvider
from ..graph.query import get_style_rules_for_platform, get_vocabulary_rules
from ..utils.text_utils import load_prompt, fill_prompt

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

# ─────────────────────────────────────────────────────────
# HEAVY ENGLISH WORD LIST — pre-filtered before LLM pass
# so the model doesn't have to hunt for them itself
# ─────────────────────────────────────────────────────────
HEAVY_ENGLISH_REPLACEMENTS: dict[str, str] = {
    "utilize": "use",
    "utilization": "use",
    "leverage": "use",
    "facilitate": "help",
    "implement": "do",
    "demonstrate": "show",
    "encounter": "face",
    "subsequently": "then",
    "consequently": "so",
    "nevertheless": "but",
    "furthermore": "also",
    "in addition to": "beyond that",
    "in order to": "to",
    "due to the fact that": "because",
    "the fact that": "that",
    "it is important to note": "",
    "it is worth mentioning": "",
    "one must consider": "",
    "this serves to": "this",
    "landscape": "",
    "navigate": "",
    "foster": "",
    "harness": "",
    "unlock": "",
    "delve": "",
    "tapestry": "",
    "synergy": "",
    "robust": "",
    "multifaceted": "",
    "nuanced approach": "approach",
    "revolutionary": "",
    "game-changing": "",
    "transformative": "",
    "cutting-edge": "",
    "best practices": "",
    "thought leader": "",
    "paradigm shift": "",
    "at the end of the day": "",
    "deep dive": "look",
    "seamless": "",
    "empower": "",
    "holistic": "",
    "innovative": "",
    "groundbreaking": "",
    "unprecedented": "",
}

AI_SPECIAL_CHARS = ["\u2014", "\u2013"]  # em dash, en dash


def _pre_clean(post: str) -> tuple[str, list[str]]:
    """Light deterministic pre-clean before the LLM pass.

    Returns the cleaned post and a list of human-readable change notes
    so the caller can log what was caught without an LLM call.
    """
    notes: list[str] = []
    cleaned = post

    # Replace heavy English words (case-insensitive, whole-word where possible)
    import re
    for heavy, replacement in HEAVY_ENGLISH_REPLACEMENTS.items():
        pattern = re.compile(re.escape(heavy), re.IGNORECASE)
        if pattern.search(cleaned):
            cleaned = pattern.sub(replacement, cleaned)
            notes.append(f"replaced '{heavy}' -> '{replacement or '[removed]'}'")

    # Strip em/en dashes
    for char in AI_SPECIAL_CHARS:
        if char in cleaned:
            cleaned = cleaned.replace(char, " ")
            notes.append(f"removed special char U+{ord(char):04X}")

    # Collapse double spaces left by removals
    cleaned = re.sub(r"  +", " ", cleaned)
    cleaned = re.sub(r" \.", ".", cleaned)
    cleaned = re.sub(r" ,", ",", cleaned)

    return cleaned.strip(), notes


def _detect_repetitions(post: str) -> list[str]:
    """Find repeated 4+ word phrases and repeated sentence-opening words."""
    import re
    from collections import Counter

    warnings: list[str] = []

    # Repeated n-grams (4-word phrases)
    words = re.findall(r"\b\w+\b", post.lower())
    for n in (4, 5, 6):
        ngrams = [" ".join(words[i : i + n]) for i in range(len(words) - n + 1)]
        counts = Counter(ngrams)
        for phrase, count in counts.items():
            if count >= 2:
                warnings.append(f"repeated {n}-gram ({count}x): '{phrase}'")

    # Repeated sentence-opening words
    sentences = re.split(r"(?<=[.!?])\s+", post.strip())
    openers = [s.split()[0].lower() for s in sentences if s.split()]
    opener_counts = Counter(openers)
    for word, count in opener_counts.items():
        if count >= 3:
            warnings.append(f"sentence opener '{word}' used {count}x")

    return warnings


def _build_viral_pattern_block(viral_context: dict | None) -> str:
    """Format viral graph context into the prompt block."""
    if not viral_context:
        return "No viral pattern data available for this topic."

    lines: list[str] = []

    hooks = viral_context.get("hooks", [])
    if hooks:
        lines.append("High-engagement OPENING structures:")
        for h in hooks[:4]:
            lines.append(f"  [{h.get('hook_name', '?')}] {h.get('template', '')}")

    patterns = viral_context.get("patterns", [])
    if patterns:
        lines.append("\nHigh-engagement STRUCTURAL patterns:")
        for p in patterns[:4]:
            lines.append(f"  - {p.get('description', str(p))}")

    pacing = viral_context.get("pacing", {})
    if pacing:
        lines.append(
            f"\nOptimal pacing: "
            f"avg paragraph length {pacing.get('avg_paragraph_words', '?')} words, "
            f"{pacing.get('line_breaks_per_100_words', '?')} breaks per 100 words"
        )

    return "\n".join(lines) if lines else "No viral pattern data available for this topic."


def humanize_post(
    post: str,
    graph,
    llm: LLMProvider,
    platform: str = "linkedin",
    personality_card: str = "",
    viral_context: dict | None = None,
) -> dict:
    """Apply full humanization pass using knowledge graph, personality, and viral patterns.

    Args:
        post: The draft post text to humanize.
        graph: Loaded founder knowledge graph.
        llm: LLM provider instance.
        platform: Target platform (affects style rule selection).
        personality_card: Raw founder personality description from the graph.
        viral_context: Optional viral graph context dict for this topic.

    Returns:
        {
            "humanized": str,          # final post text
            "pre_clean_notes": list,   # deterministic changes made before LLM
            "repetition_warnings": list, # repeated phrases detected before LLM
            "reasoning": str,          # why specific passes were prioritized
        }
    """
    style_rules = get_style_rules_for_platform(graph, platform)
    vocab = get_vocabulary_rules(graph)

    # ── Step 1: Pre-clean (deterministic, no LLM) ──
    pre_cleaned, pre_clean_notes = _pre_clean(post)
    repetition_warnings = _detect_repetitions(pre_cleaned)

    if pre_clean_notes:
        logger.info("[Humanizer] Pre-clean caught %d issues: %s", len(pre_clean_notes), pre_clean_notes)
    if repetition_warnings:
        logger.warning("[Humanizer] Repetitions detected: %s", repetition_warnings)

    # ── Step 2: Build prompt context ──
    rules_text = "\n".join(
        f"- [{r.get('rule_type', '?')}] {r.get('description', '')}"
        + (f"\n  Anti-pattern: {r['anti_pattern']}" if r.get("anti_pattern") else "")
        for r in style_rules
    ) or "No specific style rules available."

    viral_block = _build_viral_pattern_block(viral_context)

    # Build reasoning note for caller — explains which passes will be heavy
    reasoning_parts: list[str] = []
    if pre_clean_notes:
        reasoning_parts.append(f"Pre-clean removed {len(pre_clean_notes)} heavy/AI-tell instances before LLM pass.")
    if repetition_warnings:
        reasoning_parts.append(f"Repetition pass flagged: {'; '.join(repetition_warnings[:3])}.")
    if not personality_card:
        reasoning_parts.append("No personality card provided — voice lock pass will use style rules only.")
    if not viral_context:
        reasoning_parts.append("No viral context — structural patterns from graph only.")

    # ── Step 3: LLM humanization pass ──
    template = load_prompt(PROMPTS_DIR / "humanize.txt")
    prompt = fill_prompt(
        template,
        personality_card=personality_card.strip()[:3000] if personality_card else "Not provided — use style rules as the sole voice reference.",
        viral_patterns=viral_block,
        style_rules=rules_text,
        phrases_used=", ".join(vocab.get("phrases_used", [])) or "None specified.",
        phrases_never=", ".join(vocab.get("phrases_never", [])) or "None specified.",
        post=pre_cleaned,
    )

    result = llm.generate(prompt, temperature=0.55, max_tokens=2500)
    humanized = result.strip()

    # ── Step 4: Final repetition scan on output ──
    post_humanize_reps = _detect_repetitions(humanized)
    if post_humanize_reps:
        logger.warning("[Humanizer] Post-LLM repetitions still detected: %s", post_humanize_reps)
        reasoning_parts.append(f"Post-humanize repetition scan: {len(post_humanize_reps)} issue(s) remain — review manually.")

    return {
        "humanized": humanized,
        "pre_clean_notes": pre_clean_notes,
        "repetition_warnings": repetition_warnings,
        "post_humanize_repetitions": post_humanize_reps,
        "reasoning": " | ".join(reasoning_parts) if reasoning_parts else "All passes clean.",
    }