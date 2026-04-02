"""Query the viral posts knowledge graph for generation context."""

from __future__ import annotations

import logging
import sys
from difflib import SequenceMatcher

import networkx as nx

logger = logging.getLogger(__name__)


def get_viral_context_for_topic(
    viral_graph: nx.DiGraph,
    topic: str,
    creativity: float = 0.5,
) -> dict:
    """Query viral graph for context relevant to a topic.

    Args:
        viral_graph: The viral "Big Brain" graph
        topic: The generation topic
        creativity: 0.0=prescriptive (more viral patterns), 1.0=creative (fewer)

    Returns dict with hooks, structures, patterns, techniques, engagement_stats
    """
    print(f"\033[33m[ViralQuery]\033[0m get_viral_context_for_topic(topic={topic!r}, creativity={creativity})", file=sys.stderr, flush=True)
    if viral_graph is None or viral_graph.number_of_nodes() == 0:
        print(f"\033[33m[ViralQuery]\033[0m → Empty viral graph, returning empty context", file=sys.stderr, flush=True)
        return {"hooks": [], "structures": [], "patterns": [], "techniques": [], "engagement_stats": {}}

    topic_lower = topic.lower()
    topic_words = set(topic_lower.split())

    # ── Collect all node types ──
    hooks = []
    structures = []
    patterns = []
    techniques = []
    engagement_stats = {}

    for nid, data in viral_graph.nodes(data=True):
        ntype = data.get("node_type", "")

        if ntype == "hook_type":
            hooks.append({"id": nid, **{k: v for k, v in data.items() if k != "node_type"}})
        elif ntype == "structure_template":
            structures.append({"id": nid, **{k: v for k, v in data.items() if k != "node_type"}})
        elif ntype == "viral_pattern":
            patterns.append({"id": nid, **{k: v for k, v in data.items() if k != "node_type"}})
        elif ntype == "writing_technique":
            techniques.append({"id": nid, **{k: v for k, v in data.items() if k != "node_type"}})
        elif ntype == "engagement_profile":
            engagement_stats[data.get("bracket", nid)] = {k: v for k, v in data.items() if k != "node_type"}

    # ── Sort by engagement ──
    hooks.sort(key=lambda x: x.get("avg_engagement", 0), reverse=True)
    structures.sort(key=lambda x: x.get("avg_engagement", 0), reverse=True)

    # ── Apply creativity filter (fewer results at high creativity) ──
    # Low creativity (0-0.3): return all top patterns (prescriptive)
    # High creativity (0.7-1.0): return fewer, loosely
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
    print(f"\033[33m[ViralQuery]\033[0m \033[32m→ {len(result['hooks'])} hooks, {len(result['structures'])} structures, {len(result['patterns'])} patterns, {len(result['techniques'])} techniques\033[0m", file=sys.stderr, flush=True)
    return result


def format_viral_context_for_prompt(viral_context: dict, creativity: float = 0.5) -> str:
    """Format viral context into a prompt-ready string."""
    if not viral_context or not any(viral_context.get(k) for k in ["hooks", "structures", "patterns", "techniques"]):
        return "No viral pattern data available."

    sections = []

    # Hooks
    hooks = viral_context.get("hooks", [])
    if hooks:
        hook_lines = []
        for h in hooks[:5]:
            name = h.get("hook_name", "")
            template = h.get("template", "")
            eng = h.get("avg_engagement", 0)
            hook_lines.append(f"  - {name}: {template} (avg engagement: {eng})")
        sections.append("PROVEN HOOK TYPES:\n" + "\n".join(hook_lines))

    # Structures
    structures = viral_context.get("structures", [])
    if structures:
        struct_lines = []
        for s in structures[:4]:
            name = s.get("template_name", "")
            eng = s.get("avg_engagement", 0)
            struct_lines.append(f"  - {name} (avg engagement: {eng})")
        sections.append("TOP STRUCTURE TEMPLATES:\n" + "\n".join(struct_lines))

    # Patterns
    patterns = viral_context.get("patterns", [])
    if patterns:
        pat_lines = [f"  - {p.get('pattern_name', '')}: {p.get('description', '')}" for p in patterns[:5]]
        sections.append("VIRAL PATTERNS:\n" + "\n".join(pat_lines))

    # Techniques
    techniques = viral_context.get("techniques", [])
    if techniques:
        tech_lines = [f"  - {t.get('technique_name', '')}: {t.get('description', '')}" for t in techniques[:4]]
        sections.append("WRITING TECHNIQUES:\n" + "\n".join(tech_lines))

    return "\n\n".join(sections)
