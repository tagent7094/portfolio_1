"""Build the Viral Posts Knowledge Graph (Big Brain)."""

from __future__ import annotations

import logging
from statistics import mean

import networkx as nx

logger = logging.getLogger(__name__)


def build_viral_graph(extracted_data: dict) -> nx.DiGraph:
    """Build a knowledge graph from viral post extraction results.

    Args:
        extracted_data: dict with keys from run_full_viral_extraction():
            brackets, structures, hooks, patterns, techniques
    """
    graph = nx.DiGraph()

    # Central node
    graph.add_node("viral_brain", node_type="viral_brain", label="Viral Brain",
                   description="Central knowledge of what makes LinkedIn posts go viral")

    # Category hubs
    for cat_id, label in [
        ("cat_hooks", "Hook Types"),
        ("cat_structures", "Structure Templates"),
        ("cat_patterns", "Viral Patterns"),
        ("cat_techniques", "Writing Techniques"),
        ("cat_engagement", "Engagement Profiles"),
    ]:
        graph.add_node(cat_id, node_type="category", label=label)
        graph.add_edge("viral_brain", cat_id, edge_type="HAS_CATEGORY")

    # ── Hook Type Nodes ──
    hooks = extracted_data.get("hooks", [])
    for h in hooks:
        nid = h.get("id", f"hook_{hash(h.get('hook_name', ''))}")
        graph.add_node(nid,
                       node_type="hook_type",
                       hook_name=h.get("hook_name", ""),
                       template=h.get("template", ""),
                       avg_engagement=h.get("avg_engagement", 0),
                       example_hooks=h.get("example_hooks", []),
                       count=h.get("count", 0),
                       why_it_works=h.get("why_it_works", ""))
        graph.add_edge("cat_hooks", nid, edge_type="CONTAINS")

    # ── Structure Template Nodes ──
    structures = extracted_data.get("structures", [])
    for s in structures:
        nid = s.get("id", f"struct_{hash(s.get('template_name', ''))}")
        graph.add_node(nid,
                       node_type="structure_template",
                       template_name=s.get("template_name", ""),
                       structure_description=s.get("structure_description", ""),
                       count=s.get("count", 0),
                       avg_engagement=s.get("avg_engagement", 0),
                       example_post_ids=s.get("example_post_ids", []))
        graph.add_edge("cat_structures", nid, edge_type="CONTAINS")

    # ── Viral Pattern Nodes ──
    patterns = extracted_data.get("patterns", [])
    for p in patterns:
        nid = p.get("id", f"pattern_{hash(p.get('pattern_name', ''))}")
        graph.add_node(nid,
                       node_type="viral_pattern",
                       pattern_name=p.get("pattern_name", ""),
                       description=p.get("description", ""),
                       bracket=p.get("bracket", ""),
                       effectiveness=p.get("effectiveness", "medium"))
        graph.add_edge("cat_patterns", nid, edge_type="CONTAINS")

    # ── Writing Technique Nodes ──
    techniques = extracted_data.get("techniques", [])
    for t in techniques:
        nid = t.get("id", f"tech_{hash(t.get('technique_name', ''))}")
        graph.add_node(nid,
                       node_type="writing_technique",
                       technique_name=t.get("technique_name", ""),
                       description=t.get("description", ""),
                       impact=t.get("impact", "medium"),
                       example_snippet=t.get("example_snippet", ""))
        graph.add_edge("cat_techniques", nid, edge_type="CONTAINS")

    # ── Engagement Profile Nodes ──
    brackets = extracted_data.get("brackets", {})
    for bracket_name in ["mega_viral", "strong", "moderate"]:
        info = brackets.get(bracket_name, {})
        if isinstance(info, dict) and info.get("count", 0) > 0:
            nid = f"engagement_{bracket_name}"
            graph.add_node(nid,
                           node_type="engagement_profile",
                           bracket=bracket_name,
                           count=info.get("count", 0),
                           engagement_range=info.get("engagement_range", ""),
                           avg_engagement=info.get("avg_engagement", 0),
                           avg_likes=info.get("avg_likes", 0),
                           avg_comments=info.get("avg_comments", 0))
            graph.add_edge("cat_engagement", nid, edge_type="CONTAINS")

    # ── Cross-type edges ──
    _build_viral_edges(graph)

    logger.info("Viral graph built: %d nodes, %d edges", graph.number_of_nodes(), graph.number_of_edges())
    return graph


def _build_viral_edges(graph: nx.DiGraph):
    """Build cross-type edges in the viral graph."""
    hooks = [n for n, d in graph.nodes(data=True) if d.get("node_type") == "hook_type"]
    structures = [n for n, d in graph.nodes(data=True) if d.get("node_type") == "structure_template"]
    patterns = [n for n, d in graph.nodes(data=True) if d.get("node_type") == "viral_pattern"]
    techniques = [n for n, d in graph.nodes(data=True) if d.get("node_type") == "writing_technique"]
    engagements = [n for n, d in graph.nodes(data=True) if d.get("node_type") == "engagement_profile"]

    # Hook ↔ Pattern: keyword overlap
    for h in hooks:
        h_data = graph.nodes[h]
        h_words = set((h_data.get("hook_name", "") + " " + h_data.get("template", "")).lower().split())
        for p in patterns:
            p_data = graph.nodes[p]
            p_words = set((p_data.get("pattern_name", "") + " " + p_data.get("description", "")).lower().split())
            if len(h_words & p_words) >= 2:
                graph.add_edge(h, p, edge_type="EXHIBITS_PATTERN")

    # Pattern → Engagement: bracket correlation
    for p in patterns:
        p_data = graph.nodes[p]
        bracket = p_data.get("bracket", "")
        for e in engagements:
            e_data = graph.nodes[e]
            if e_data.get("bracket") == bracket:
                graph.add_edge(p, e, edge_type="CORRELATES_WITH")

    # Technique → Pattern: keyword overlap
    for t in techniques:
        t_data = graph.nodes[t]
        t_words = set((t_data.get("technique_name", "") + " " + t_data.get("description", "")).lower().split())
        for p in patterns:
            p_data = graph.nodes[p]
            p_words = set((p_data.get("pattern_name", "") + " " + p_data.get("description", "")).lower().split())
            if len(t_words & p_words) >= 2:
                graph.add_edge(t, p, edge_type="TECHNIQUE_IN_PATTERN")
