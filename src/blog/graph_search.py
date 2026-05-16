"""Graph-enriched web search prompt builder.

Replaces the hardcoded web search queries with prompts that draw on the
full founder knowledge graph — beliefs, stories, contrast pairs, thinking
models, cast, scenes, milestones — so the LLM generates contextual,
founder-specific search queries every time.
"""

from __future__ import annotations

import re
import logging
from pathlib import Path

import networkx as nx

from ..graph.conviction_query import (
    get_deep_founder_context_v2,
    neighbors_for_topic,
    top_beliefs_by_conviction,
    top_milestones,
)

logger = logging.getLogger(__name__)


def build_graph_enriched_search_prompt(
    founder_slug: str,
    topic: str,
    graph: nx.DiGraph,
    personality_card: str,
) -> str:
    """Build a rich, context-aware prompt for web search using the full founder graph."""

    ctx = get_deep_founder_context_v2(graph, "blog", topic)

    founder_name = founder_slug.replace("_", " ").title()
    card_first = (personality_card or "").split("\n")[0]
    company_match = re.search(
        r'(?:of|at|founded|leads?|CEO of|co-?founder of)\s+([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*)',
        card_first,
    )
    company_name = company_match.group(1) if company_match else ""

    beliefs = ctx.get("beliefs", [])[:10]
    beliefs_str = "\n".join(
        f"  - {b.get('topic', '')}: {b.get('stance', '')}"
        for b in beliefs if b.get("topic")
    )

    stories = ctx.get("stories", [])[:5]
    stories_str = "\n".join(
        f"  - {s.get('title', '')}: {(s.get('summary', '') or '')[:100]}"
        for s in stories if s.get("title")
    )

    contrast_pairs = ctx.get("contrast_pairs", [])[:5]
    contrasts_str = "\n".join(
        f"  - {c.get('left', '')} vs {c.get('right', '')}: {(c.get('description', '') or '')[:80]}"
        for c in contrast_pairs
    )

    thinking_models = ctx.get("thinking_models", [])[:5]
    models_str = "\n".join(
        f"  - {m.get('name', '')}: {(m.get('description', '') or '')[:80]}"
        for m in thinking_models if m.get("name")
    )

    cast = ctx.get("cast", [])[:5]
    cast_str = ", ".join(
        c.get("name") or c.get("label", "") for c in cast
    ) if cast else ""

    milestones = ctx.get("milestones", [])[:5]
    milestones_str = "\n".join(
        f"  - {m.get('label', '') or m.get('title', '')} ({m.get('date', '') or m.get('year', '')})"
        for m in milestones if m.get("label") or m.get("title")
    )

    topic_neighbors = neighbors_for_topic(graph, topic) if topic else {}
    neighbor_str = ""
    for edge_type, nodes in topic_neighbors.items():
        if nodes:
            items = ", ".join(
                n.get("label", "") or n.get("name", "") or n.get("title", "")
                for n in nodes[:3]
            )
            if items:
                neighbor_str += f"  - {edge_type}: {items}\n"

    sections = [
        f"You are researching current topics for {founder_name}"
        + (f" (founder/CEO of {company_name})" if company_name else "")
        + ".",
    ]

    if personality_card:
        sections.append(f"\n## FOUNDER PROFILE\n{personality_card[:1500]}")

    if beliefs_str:
        sections.append(f"\n## CORE BELIEFS & POSITIONS\n{beliefs_str}")

    if stories_str:
        sections.append(f"\n## KEY STORIES & EXPERIENCES\n{stories_str}")

    if contrasts_str:
        sections.append(f"\n## SIGNATURE CONTRAST PAIRS\n{contrasts_str}")

    if models_str:
        sections.append(f"\n## THINKING MODELS\n{models_str}")

    if cast_str:
        sections.append(f"\n## KEY PEOPLE IN THEIR WORLD\n  {cast_str}")

    if milestones_str:
        sections.append(f"\n## MILESTONES\n{milestones_str}")

    if neighbor_str:
        sections.append(f"\n## TOPIC-SPECIFIC GRAPH CONNECTIONS (for '{topic}')\n{neighbor_str}")

    if topic:
        sections.append(f"\n## BLOG TOPIC\n  {topic}")

    sections.append("""
## TASK

Based on this founder's complete profile, search the web for:
1. Recent news, developments, or data points related to their specific beliefs and positions
2. Trending conversations in their exact domain that they could contribute to
3. Contrarian viewpoints or emerging debates that align with their known contrast pairs
4. Recent activity or mentions of the founder, their company, or key people in their network
5. Industry statistics or reports that support or challenge their documented beliefs

Generate diverse, specific search queries — NOT generic industry searches. Each query should reflect this founder's unique perspective, positions, or network.

Summarize findings as JSON:
```json
{
  "trending_topics": ["topic1", "topic2"],
  "facts": [{"fact": "...", "source": "...", "relevance": "..."}],
  "contrarian_angles": ["angle1", "angle2"],
  "founder_news": [{"headline": "...", "source": "...", "date": "..."}]
}
```""")

    return "\n".join(sections)
