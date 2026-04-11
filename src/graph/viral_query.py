"""Query the viral posts knowledge graph for generation context.

Changes from original:
- Issue #27: Topic parameter now actually filters results instead of being ignored
- Added relevance scoring for hooks and patterns
- Improved creativity scaling
"""

from __future__ import annotations

import logging
import sys

import networkx as nx

from .builder import _tokenize

logger = logging.getLogger(__name__)


def _relevance_score(node_data: dict, topic_tokens: set[str]) -> float:
    """Score a viral node's relevance to a topic."""
    if not topic_tokens:
        return 1.0  # No topic filter = everything relevant

    text_fields = []
    for field in ("hook_name", "template", "template_name", "structure_description",
                  "pattern_name", "description", "technique_name"):
        val = node_data.get(field, "")
        if val:
            text_fields.append(val)

    combined = " ".join(text_fields)
    node_tokens = _tokenize(combined)

    if not node_tokens:
        return 0.1

    overlap = len(topic_tokens & node_tokens)
    return overlap / max(len(topic_tokens), 1)


def get_viral_context_for_topic(
    viral_graph: nx.DiGraph,
    topic: str,
    creativity: float = 0.5,
) -> dict:
    """Query viral graph for context relevant to a topic.

    Now actually uses the topic parameter to rank and filter results.
    """
    _log(f"get_viral_context_for_topic(topic={topic!r}, creativity={creativity})")

    if viral_graph is None or viral_graph.number_of_nodes() == 0:
        _log("→ Empty viral graph")
        return {"hooks": [], "structures": [], "patterns": [], "techniques": [], "engagement_stats": {}}

    topic_tokens = _tokenize(topic) if topic else set()

    hooks = []
    structures = []
    patterns = []
    techniques = []
    engagement_stats = {}

    for nid, data in viral_graph.nodes(data=True):
        ntype = data.get("node_type", "")
        relevance = _relevance_score(data, topic_tokens)
        entry = {"id": nid, "_relevance": relevance,
                 **{k: v for k, v in data.items() if k != "node_type"}}

        if ntype == "hook_type":
            hooks.append(entry)
        elif ntype == "structure_template":
            structures.append(entry)
        elif ntype == "viral_pattern":
            patterns.append(entry)
        elif ntype == "writing_technique":
            techniques.append(entry)
        elif ntype == "engagement_profile":
            engagement_stats[data.get("bracket", nid)] = {k: v for k, v in data.items() if k != "node_type"}

    # Sort by relevance first, then engagement
    def _sort_key(x):
        return (x.get("_relevance", 0), x.get("avg_engagement", 0))

    hooks.sort(key=_sort_key, reverse=True)
    structures.sort(key=_sort_key, reverse=True)
    patterns.sort(key=lambda x: x.get("_relevance", 0), reverse=True)
    techniques.sort(key=lambda x: x.get("_relevance", 0), reverse=True)

    # Creativity-based limits
    max_hooks = max(2, int(10 * (1 - creativity * 0.7)))
    max_structures = max(2, int(8 * (1 - creativity * 0.7)))
    max_patterns = max(2, int(10 * (1 - creativity * 0.7)))
    max_techniques = max(2, int(8 * (1 - creativity * 0.7)))

    result = {
        "hooks": hooks[:max_hooks],
        "structures": structures[:max_structures],
        "patterns": patterns[:max_patterns],
        "techniques": techniques[:max_techniques],
        "engagement_stats": engagement_stats,
    }
    _log(f"→ {len(result['hooks'])}H {len(result['structures'])}S "
         f"{len(result['patterns'])}P {len(result['techniques'])}T")
    return result


def format_viral_context_for_prompt(viral_context: dict, creativity: float = 0.5) -> str:
    """Format viral context into a prompt-ready string."""
    if not viral_context or not any(viral_context.get(k) for k in ["hooks", "structures", "patterns", "techniques"]):
        return "No viral pattern data available."

    sections = []

    hooks = viral_context.get("hooks", [])
    if hooks:
        lines = []
        for h in hooks[:5]:
            name = h.get("hook_name", "")
            template = h.get("template", "")
            eng = h.get("avg_engagement", 0)
            lines.append(f"  - {name}: {template} (avg engagement: {eng})")
        sections.append("PROVEN HOOK TYPES:\n" + "\n".join(lines))

    structures = viral_context.get("structures", [])
    if structures:
        lines = []
        for s in structures[:4]:
            name = s.get("template_name", "")
            desc = s.get("structure_description", "")
            eng = s.get("avg_engagement", 0)
            lines.append(f"  - {name}: {desc[:80]} (avg engagement: {eng})")
        sections.append("TOP STRUCTURE TEMPLATES:\n" + "\n".join(lines))

    patterns = viral_context.get("patterns", [])
    if patterns:
        lines = [f"  - {p.get('pattern_name', '')}: {p.get('description', '')}" for p in patterns[:5]]
        sections.append("VIRAL PATTERNS:\n" + "\n".join(lines))

    techniques = viral_context.get("techniques", [])
    if techniques:
        lines = [f"  - {t.get('technique_name', '')}: {t.get('description', '')}" for t in techniques[:4]]
        sections.append("WRITING TECHNIQUES:\n" + "\n".join(lines))

    return "\n\n".join(sections)


def _log(msg: str):
    print(f"\033[33m[ViralQuery]\033[0m {msg}", file=sys.stderr, flush=True)