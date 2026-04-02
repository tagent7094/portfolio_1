"""Generate post variants using knowledge graph context and narrative engines.

Enhanced to:
- Use the narrative_engines module for diverse structural approaches
- Pass viral context block from creativity slider
- Forward post_architecture_hint from narrative extraction
- Support configurable engine selection
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import yaml

from ..llm.base import LLMProvider
from ..graph.query import get_full_context, get_style_rules_for_platform
from ..utils.text_utils import load_prompt, fill_prompt
from .narrative_engines import NARRATIVE_ENGINES, generate_with_engine, get_engines_subset

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

# Default engines for variant generation (balanced mix of approaches)
DEFAULT_ENGINE_IDS = [
    "bold_declarative",
    "story_first",
    "concession_counter",
    "tension_bridge",
    "anti_post",
]


def _load_platform_rules(platform: str) -> str:
    """Load platform constraints from quality rules config."""
    config_path = Path(__file__).parent.parent.parent / "config" / "quality-rules.yaml"
    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f)
        rules = config.get("platform_rules", {}).get(platform, {})
        parts = []
        if rules.get("min_length"):
            parts.append(f"Min length: {rules['min_length']}")
        if rules.get("max_length"):
            parts.append(f"Max length: {rules['max_length']}")
        if rules.get("format"):
            parts.append(f"Format: {rules['format']}")
        if rules.get("hashtags"):
            parts.append(f"Hashtags: {rules['hashtags']}")
        return ", ".join(parts) if parts else "Standard format."
    return "Standard format."


def generate_post(
    narrative: dict,
    strategy: str,
    platform: str,
    graph,
    llm: LLMProvider,
    topic: str = "",
    viral_context_block: str = "",
) -> dict:
    """Generate a single post variant using a strategy string.

    This is the legacy interface — for new code, prefer generate_with_engine()
    from narrative_engines.py which uses the full engine definitions.
    """
    context = get_full_context(graph, topic or narrative.get("narrative", ""), platform)
    style_rules = context["style_rules"]
    vocab = context["vocabulary"]

    template = load_prompt(PROMPTS_DIR / "generate_post.txt")

    beliefs_text = "\n".join(
        f"- {b.get('topic', '?')}: {b.get('stance', '?')}" for b in context["beliefs"][:10]
    ) or "No specific beliefs found."

    stories_text = "\n".join(
        f"- {s.get('title', '?')}: {s.get('summary', '?')}" for s in context["stories"][:5]
    ) or "No specific stories found."

    anti_patterns = []
    for r in style_rules:
        if r.get("anti_pattern"):
            anti_patterns.append(f"- NEVER: {r['anti_pattern']}")

    # Build narrative text with architecture hint if available
    narrative_text = narrative.get("narrative", "") + "\n" + narrative.get("angle", "")
    if narrative.get("post_architecture_hint"):
        narrative_text += f"\n\nStructural hint: {narrative['post_architecture_hint']}"

    prompt = fill_prompt(
        template,
        platform=platform,
        personality_card=context["personality_card"] or "No personality card available.",
        narrative=narrative_text,
        beliefs=beliefs_text,
        stories=stories_text,
        strategy=strategy,
        viral_context_block=viral_context_block or context.get("viral_context_block", ""),
        opening_rules=_format_rules(style_rules, "opening"),
        closing_rules=_format_rules(style_rules, "closing"),
        rhythm_rules=_format_rules(style_rules, "rhythm"),
        phrases_used=", ".join(vocab.get("phrases_used", [])) or "None specified.",
        phrases_never=", ".join(vocab.get("phrases_never", [])) or "None specified.",
        punctuation_rules=_format_rules(style_rules, "punctuation"),
        pronoun_rules=json.dumps(vocab.get("pronoun_rules", {})),
        platform_rules=_load_platform_rules(platform),
        anti_patterns="\n".join(anti_patterns) or "None specified.",
    )

    post_text = llm.generate(prompt, temperature=0.8, max_tokens=2000)

    return {
        "id": f"{strategy[:20]}_{platform}",
        "text": post_text.strip(),
        "strategy": strategy,
        "engine_id": strategy[:20],
        "engine_name": strategy,
        "platform": platform,
    }


def _format_rules(rules: list[dict], rule_type: str) -> str:
    """Format style rules of a specific type into a string."""
    matching = [r for r in rules if r.get("rule_type") == rule_type]
    if not matching:
        return "No specific rules."
    return "\n".join(f"- {r.get('description', '')}" for r in matching)


def generate_post_variants(
    narrative: dict,
    platform: str,
    graph,
    llm: LLMProvider,
    topic: str = "",
    engine_ids: list[str] | None = None,
    viral_context_block: str = "",
    token_callback=None,
) -> list[dict]:
    """Generate multiple post variants using different narrative engines.

    Args:
        narrative: The winning narrative from extraction/scoring
        platform: Target platform (linkedin, twitter, etc.)
        graph: Knowledge graph
        llm: LLM provider
        topic: Optional topic string for context retrieval
        engine_ids: Optional list of engine IDs to use (defaults to DEFAULT_ENGINE_IDS)
        viral_context_block: Pre-built viral context from creativity slider
        token_callback: Optional callable for streaming tokens

    Returns:
        List of post dicts with id, text, engine_id, engine_name, platform
    """
    # Get engines
    ids_to_use = engine_ids or DEFAULT_ENGINE_IDS
    engines = get_engines_subset(ids_to_use)

    if not engines:
        logger.warning("No matching engines found for IDs: %s", ids_to_use)
        engines = NARRATIVE_ENGINES[:3]  # Fallback to first 3

    # Build context once (shared across all engines)
    context = get_full_context(graph, topic or narrative.get("narrative", ""), platform)
    context["viral_context_block"] = viral_context_block

    print(
        f"\033[34m[PostGenerator]\033[0m \033[1mGenerating {len(engines)} variants "
        f"for platform={platform}\033[0m",
        file=sys.stderr, flush=True,
    )

    posts = []
    for engine in engines:
        logger.info("Generating post with engine: %s (%s)", engine["name"], engine["id"])
        post = generate_with_engine(
            engine=engine,
            narrative=narrative,
            platform=platform,
            context=context,
            llm=llm,
            token_callback=token_callback,
        )
        posts.append(post)

    print(
        f"\033[34m[PostGenerator]\033[0m \033[32m→ Generated {len(posts)} variants\033[0m",
        file=sys.stderr, flush=True,
    )

    return posts
