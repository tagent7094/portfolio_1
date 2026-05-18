"""Graph-RAG for batch generation.

Two layers:
1. `build_personality_card_from_graph` — synthesize a personality_card when
   the founder's `personality-card.md` file is missing. Pulls top beliefs,
   contrast_pairs, thinking_models, stories, cast, scenes from `founder_ctx`.
2. `retrieve_graph_context` — at any generation stage, score-rank graph nodes
   by keyword overlap with the current context (source post + post argument
   + assigned anchor). Returns the top-k beliefs/stories/etc. that the LLM
   should pull from when writing THIS post.

Both helpers read from `state.founder_ctx`, which is populated by
`get_deep_founder_context_v2` during `load_founder_state`. No new graph
loading happens here — we re-rank the lists that already exist.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


_STOPWORDS = {
    "the", "a", "an", "of", "and", "or", "for", "in", "on", "at",
    "to", "with", "from", "by", "is", "are", "was", "were", "be",
    "been", "being", "this", "that", "these", "those", "it", "its",
    "as", "if", "then", "than", "but", "not", "no", "you", "your",
    "we", "our", "they", "them", "their", "i", "me", "my", "mine",
    "what", "when", "where", "why", "how", "who", "which",
    "do", "does", "did", "has", "have", "had", "can", "could",
    "will", "would", "should", "may", "might", "must", "into",
    "about", "any", "all", "some", "more", "most", "less", "many",
}


def _tokenize(text: str) -> set[str]:
    """Lowercase, strip punctuation, drop short tokens + stopwords."""
    if not text:
        return set()
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_'-]+", text.lower())
    return {t for t in tokens if len(t) >= 3 and t not in _STOPWORDS}


def _node_text(node: dict) -> str:
    """Concatenate the searchable fields of a graph node."""
    return " ".join(
        str(node.get(k, "")) for k in (
            "label", "title", "name", "stance", "summary",
            "description", "left", "right", "topic",
        )
    ).strip()


def _score_node(node: dict, query_tokens: set[str], boost_field: str = "") -> float:
    """Score = number of overlapping tokens + small boost from a numeric field."""
    if not query_tokens:
        # No query → fall back to whatever the boost field tells us.
        if boost_field:
            return float(node.get(boost_field, 0) or 0)
        return 0.0
    node_tokens = _tokenize(_node_text(node))
    if not node_tokens:
        return 0.0
    overlap = len(query_tokens & node_tokens)
    if overlap == 0:
        return 0.0
    boost = float(node.get(boost_field, 0) or 0) if boost_field else 0.0
    return float(overlap) + 0.01 * boost


def retrieve_graph_context(
    founder_ctx: dict,
    query_text: str,
    k_beliefs: int = 5,
    k_stories: int = 3,
    k_thinking_models: int = 3,
    k_contrast_pairs: int = 3,
    k_cast: int = 3,
    k_scenes: int = 2,
    k_milestones: int = 2,
) -> dict:
    """Score-rank graph nodes by overlap with query_text.

    Returns a dict with top-k of each type. When `query_text` is empty or
    matches nothing, falls back to graph-order ranking (conviction-sorted for
    beliefs, engagement-sorted for stories — both pre-sorted by the v2 query).
    """
    q_tokens = _tokenize(query_text)

    def _topk(nodes: list, k: int, boost: str = "") -> list:
        if not nodes:
            return []
        scored = sorted(
            nodes,
            key=lambda n: (_score_node(n, q_tokens, boost), float(n.get(boost, 0) or 0) if boost else 0),
            reverse=True,
        )
        return scored[:k]

    return {
        "beliefs": _topk(founder_ctx.get("beliefs", []) or [], k_beliefs, boost="conviction"),
        "stories": _topk(founder_ctx.get("stories", []) or [], k_stories, boost="engagement"),
        "thinking_models": _topk(founder_ctx.get("thinking_models", []) or [], k_thinking_models, boost="priority"),
        "contrast_pairs": _topk(founder_ctx.get("contrast_pairs", []) or [], k_contrast_pairs),
        "cast": _topk(founder_ctx.get("cast", []) or [], k_cast),
        "scenes": _topk(founder_ctx.get("scenes", []) or [], k_scenes),
        "milestones": _topk(founder_ctx.get("milestones", []) or [], k_milestones),
        "query_tokens_matched": len(q_tokens),
    }


def format_graph_rag_for_prompt(context: dict, header: str = "") -> str:
    """Render retrieve_graph_context() output as a compact prompt block."""
    parts: list[str] = []
    if header:
        parts.append(header)

    if context.get("beliefs"):
        parts.append("BELIEFS (relevant to this post, conviction-weighted):")
        for b in context["beliefs"]:
            label = b.get("label", "") or b.get("topic", "")
            stance = b.get("stance", "") or b.get("description", "")
            conv = b.get("conviction", 0)
            parts.append(f"- {label} (conviction {conv:.2f}): {stance}")

    if context.get("contrast_pairs"):
        parts.append("\nTENSIONS the founder navigates:")
        for c in context["contrast_pairs"]:
            left = c.get("left", "")
            right = c.get("right", "")
            desc = c.get("description", "")
            parts.append(f"- {left} vs {right} — {desc}")

    if context.get("stories"):
        parts.append("\nSTORIES (engagement-ranked, use as first-degree anchors):")
        for s in context["stories"]:
            label = s.get("label", "") or s.get("title", "")
            summary = s.get("summary", "") or s.get("description", "")
            parts.append(f"- {label}: {summary}")

    if context.get("thinking_models"):
        parts.append("\nTHINKING MODELS:")
        for m in context["thinking_models"]:
            name = m.get("name", "") or m.get("label", "")
            desc = m.get("description", "")
            parts.append(f"- {name}: {desc}")

    if context.get("cast"):
        parts.append("\nNAMED PEOPLE (cast) — use ONLY if documented:")
        for c in context["cast"]:
            name = c.get("name", "") or c.get("label", "")
            desc = c.get("description", "")
            parts.append(f"- {name}: {desc}")

    if context.get("scenes"):
        parts.append("\nSIGNATURE SCENES:")
        for s in context["scenes"]:
            name = s.get("name", "") or s.get("label", "")
            desc = s.get("description", "")
            parts.append(f"- {name}: {desc}")

    if context.get("milestones"):
        parts.append("\nDATED MILESTONES:")
        for m in context["milestones"]:
            label = m.get("label", "") or m.get("title", "")
            desc = m.get("description", "")
            parts.append(f"- {label}: {desc}")

    return "\n".join(parts).strip()


def build_personality_card_from_graph(
    founder_ctx: dict,
    display_name: str,
    founder_slug: str,
) -> str:
    """Synthesize a personality_card markdown from graph nodes.

    Used when `personality-card.md` is missing or empty. Output is a structured
    markdown that gets dropped into `state.personality_card` and flows through
    `{personality_card}` in 01_voice_load.txt.
    """
    beliefs = (founder_ctx.get("beliefs", []) or [])[:8]
    contrasts = (founder_ctx.get("contrast_pairs", []) or [])[:5]
    models = (founder_ctx.get("thinking_models", []) or [])[:5]
    stories = (founder_ctx.get("stories", []) or [])[:5]
    cast = (founder_ctx.get("cast", []) or [])[:5]
    scenes = (founder_ctx.get("scenes", []) or [])[:3]
    milestones = (founder_ctx.get("milestones", []) or [])[:5]

    name = display_name or founder_slug.title()
    lines: list[str] = [f"# {name} — Personality Card (synthesized from graph)\n"]

    if beliefs:
        lines.append("## Core Beliefs (conviction-ranked)\n")
        for b in beliefs:
            label = b.get("label", "")
            stance = b.get("stance", "") or b.get("description", "")
            conv = b.get("conviction", 0)
            if label:
                lines.append(f"- **{label}** (conviction {conv:.2f}): {stance}")
        lines.append("")

    if contrasts:
        lines.append("## Tensions the Founder Navigates\n")
        for c in contrasts:
            left = c.get("left", "")
            right = c.get("right", "")
            desc = c.get("description", "")
            if left or right:
                lines.append(f"- **{left} vs {right}** — {desc}")
        lines.append("")

    if models:
        lines.append("## Thinking Models\n")
        for m in models:
            n = m.get("name", "") or m.get("label", "")
            desc = m.get("description", "")
            if n:
                lines.append(f"- **{n}**: {desc}")
        lines.append("")

    if stories:
        lines.append("## Recurring Stories\n")
        for s in stories:
            label = s.get("label", "") or s.get("title", "")
            summary = s.get("summary", "") or s.get("description", "")
            if label:
                lines.append(f"- **{label}** — {summary}")
        lines.append("")

    if cast:
        lines.append("## Cast (named people in their orbit)\n")
        for c in cast:
            n = c.get("name", "") or c.get("label", "")
            desc = c.get("description", "")
            if n:
                lines.append(f"- **{n}** — {desc}")
        lines.append("")

    if scenes:
        lines.append("## Signature Scenes\n")
        for s in scenes:
            n = s.get("name", "") or s.get("label", "")
            desc = s.get("description", "")
            if n:
                lines.append(f"- **{n}** — {desc}")
        lines.append("")

    if milestones:
        lines.append("## Dated Milestones\n")
        for m in milestones:
            label = m.get("label", "") or m.get("title", "")
            desc = m.get("description", "")
            if label:
                lines.append(f"- **{label}** — {desc}")
        lines.append("")

    out = "\n".join(lines).strip()
    logger.info(
        "[graph_rag] Synthesized personality_card for %s: %d chars from "
        "%d beliefs, %d contrasts, %d models, %d stories",
        founder_slug, len(out), len(beliefs), len(contrasts), len(models), len(stories),
    )
    return out


def graph_signal_summary(founder_ctx: dict) -> dict:
    """Return a small summary of what's available in the graph — used for logging."""
    return {
        "beliefs": len(founder_ctx.get("beliefs", []) or []),
        "stories": len(founder_ctx.get("stories", []) or []),
        "cast": len(founder_ctx.get("cast", []) or []),
        "scenes": len(founder_ctx.get("scenes", []) or []),
        "milestones": len(founder_ctx.get("milestones", []) or []),
        "contrast_pairs": len(founder_ctx.get("contrast_pairs", []) or []),
        "thinking_models": len(founder_ctx.get("thinking_models", []) or []),
        "style_rules": len(founder_ctx.get("style_rules", []) or []),
        "vocabulary_use": len((founder_ctx.get("vocabulary") or {}).get("phrases_used", [])),
        "vocabulary_never": len((founder_ctx.get("vocabulary") or {}).get("phrases_never", [])),
    }
