"""Creativity slider logic — controls viral pattern adherence, temperature, and anti-slop strictness."""

from __future__ import annotations


def creativity_to_temperature(creativity: float) -> float:
    """Map creativity 0.0-1.0 to LLM temperature.

    Low creativity → lower temperature (more deterministic, follows patterns)
    High creativity → higher temperature (more creative, surprising)
    """
    return 0.5 + (creativity * 0.5)  # Range: 0.5 to 1.0


def build_creativity_instructions(creativity: float, viral_context_text: str) -> str:
    """Build prompt instructions based on creativity level.

    At ALL creativity levels, anti-slop rules apply. The creativity slider
    controls how closely to follow viral patterns — not whether the output
    should sound human (it always should).

    Args:
        creativity: 0.0 (follow patterns) to 1.0 (break rules)
        viral_context_text: Formatted viral patterns from format_viral_context_for_prompt()
    """
    # Anti-slop block is constant across all levels
    anti_slop_block = (
        "\n\n## ANTI-AI RULES (apply at ALL creativity levels)\n"
        "Regardless of how closely you follow viral patterns, the post must sound "
        "like a specific human wrote it. These rules are non-negotiable:\n"
        "- No 'In today's [anything]' / 'In the world of [anything]' openings\n"
        "- No 'Here's the thing' / 'Let me tell you' / 'Hot take:' / 'Unpopular opinion:'\n"
        "- No 'landscape' / 'navigate' / 'leverage' / 'foster' / 'harness' / 'unlock' / 'elevate'\n"
        "- No 'Let that sink in' / 'Read that again' / 'Game-changer'\n"
        "- No perfect parallel structure in consecutive sentences\n"
        "- No emoji as bullet points\n"
        "- At least one concrete, specific detail (number, name, date, place)\n"
        "- Sentence length must vary — not every sentence the same rhythm\n"
        "- At least one moment of imperfection: an aside, a rough transition, "
        "a sentence that prioritizes personality over polish\n"
    )

    if creativity <= 0.3:
        pattern_block = (
            "## VIRAL PATTERN GUIDANCE (HIGH PRIORITY — follow closely)\n"
            "You MUST closely follow the proven viral patterns below. "
            "Mirror the structure, hook style, and engagement techniques. "
            "The post should feel like it belongs among the top-performing posts "
            "in terms of structure — but it must still sound like a real human, "
            "not a template fill-in.\n\n"
            f"{viral_context_text}\n\n"
            "INSTRUCTION: Follow these patterns as closely as possible while maintaining "
            "the founder's authentic voice. Structure can be borrowed; voice cannot."
        )
    elif creativity <= 0.7:
        pattern_block = (
            "## VIRAL PATTERN REFERENCE (use as inspiration, not template)\n"
            "Use these proven viral patterns as reference and inspiration, "
            "but feel free to adapt, combine, or subvert them in original ways. "
            "The goal is to balance viral effectiveness with authentic, distinctive expression. "
            "If following a pattern makes the post sound generic, break the pattern.\n\n"
            f"{viral_context_text}\n\n"
            "INSTRUCTION: Use these patterns as a starting framework, "
            "but bring your own creative interpretation. The post should "
            "feel like the founder wrote it, not like they used a content template."
        )
    else:
        pattern_block = (
            "## VIRAL PATTERN CONTEXT (background awareness only)\n"
            "Here are some patterns that perform well on LinkedIn. "
            "You may reference them loosely, but prioritize originality and creative risk. "
            "Break conventions deliberately if it serves the message. Be surprising. "
            "The best posts at high creativity feel like nothing else in the feed — "
            "not because they're random, but because they have a distinctive voice "
            "and structure that doesn't follow any template.\n\n"
            f"{viral_context_text}\n\n"
            "INSTRUCTION: Be creatively bold. These patterns exist as background awareness — "
            "not as templates. The post should feel like the founder had a genuine thought "
            "and wrote it down, not like they're 'creating content.'"
        )

    return pattern_block + anti_slop_block
