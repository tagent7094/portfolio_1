"""Conviction-weighted and edge-aware graph retrieval.

The original `get_deep_founder_context` returns ALL beliefs/stories/contrast_pairs/
thinking_models without considering the new node types (cast, scene, milestone) or
the conviction/edge structure of richer graphs (like the 1,646-node alok graph).

This module adds:
- conviction-weighted belief retrieval
- cast / scene / milestone extraction
- one-hop edge-aware retrieval for topic-aware generation
- a v2 deep-context function that supersedes the v1 with strict back-compat
"""

from __future__ import annotations

from typing import Any

import networkx as nx

from .query import (
    get_personality_card,
    get_style_rules_for_platform,
    get_vocabulary_rules,
)


_DEFAULT_EDGE_TYPES = (
    "POSITIONS",
    "DEMONSTRATES",
    "EXEMPLIFIED_BY",
    "BEST_FOR",
    "SUPPORTS",
    "INFORMS",
)


def _conviction_score(data: dict) -> float:
    """Read the conviction field with fallbacks across graph schemas."""
    for key in ("conviction", "confidence", "priority"):
        v = data.get(key)
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return 0.0


def _node_entries(graph: nx.DiGraph, node_type: str) -> list[dict]:
    """Collect nodes whose type matches.

    Accepts both schemas: `node_type` (legacy NetworkX builder) and `type`
    (alok-kumar pipeline graph). Returns entries with `node_id` set.
    """
    out = []
    for node_id, data in graph.nodes(data=True):
        nt = data.get("node_type") or data.get("type")
        if nt == node_type:
            entry = {**data, "node_id": node_id}
            out.append(entry)
    return out


def top_beliefs_by_conviction(graph: nx.DiGraph, k: int = 15) -> list[dict]:
    """Return the top-k beliefs sorted by conviction score (descending)."""
    beliefs = _node_entries(graph, "belief")
    beliefs.sort(key=_conviction_score, reverse=True)
    return beliefs[:k]


def top_cast_and_scenes(
    graph: nx.DiGraph, k_cast: int = 10, k_scenes: int = 5
) -> tuple[list[dict], list[dict]]:
    """Extract `cast` and `scene` nodes — previously dropped by v1 deep context.

    Cast nodes represent named people in the founder's orbit; scene nodes are
    physical/narrative settings. Both are first-class entities that the LLM
    should be able to draw from when generating posts (instead of inventing).
    """
    cast = _node_entries(graph, "cast")
    scenes = _node_entries(graph, "scene")
    # Cast often has no conviction; sort by in-degree as a proxy for prominence.
    cast.sort(key=lambda c: graph.in_degree(c.get("node_id", "")), reverse=True)
    scenes.sort(key=lambda s: graph.in_degree(s.get("node_id", "")), reverse=True)
    return cast[:k_cast], scenes[:k_scenes]


def top_milestones(graph: nx.DiGraph, k: int = 10) -> list[dict]:
    """Return milestone nodes (dated events). Used for bio generation."""
    milestones = _node_entries(graph, "milestone")
    # Sort by date when present; otherwise leave in graph order.
    milestones.sort(key=lambda m: str(m.get("date") or m.get("year") or ""), reverse=True)
    return milestones[:k]


def neighbors_for_topic(
    graph: nx.DiGraph,
    topic: str,
    edge_types: tuple[str, ...] = _DEFAULT_EDGE_TYPES,
    k: int = 10,
) -> dict[str, list[dict]]:
    """One-hop BFS from topic-matched belief nodes filtered by edge type.

    Returns `{edge_type: [neighbor_node, ...]}`. Useful when generating a post
    on a specific topic — the LLM gets exactly the nodes that POSITION that
    topic, DEMONSTRATE it, are EXEMPLIFIED_BY it, etc.

    Returns empty dict if topic is empty or no nodes match.
    """
    if not topic:
        return {}
    topic_lower = topic.lower()
    matched_nodes: list[str] = []
    for node_id, data in graph.nodes(data=True):
        nt = data.get("node_type") or data.get("type")
        if nt != "belief":
            continue
        text = " ".join(
            str(data.get(field, ""))
            for field in ("topic", "stance", "summary", "description", "label")
        ).lower()
        if topic_lower in text:
            matched_nodes.append(node_id)

    result: dict[str, list[dict]] = {et.upper(): [] for et in edge_types}
    seen: set[tuple[str, str]] = set()
    for src in matched_nodes:
        for nbr in graph.successors(src):
            edge_data = graph.get_edge_data(src, nbr) or {}
            edge_type = (edge_data.get("edge_type") or edge_data.get("type") or "").upper()
            if edge_type not in result:
                continue
            key = (edge_type, nbr)
            if key in seen:
                continue
            seen.add(key)
            nbr_data = dict(graph.nodes[nbr])
            nbr_data["node_id"] = nbr
            result[edge_type].append(nbr_data)

    for et in result:
        result[et] = result[et][:k]
    return result


def get_deep_founder_context_v2(
    graph: nx.DiGraph, platform: str, topic: str | None = None
) -> dict:
    """Supersedes `get_deep_founder_context` with conviction sort + cast/scenes/milestones.

    Returns ALL the v1 keys (back-compat) plus:
        cast, scenes, milestones, top_beliefs_by_conviction, topic_neighbors
    """
    beliefs = _node_entries(graph, "belief")
    stories = _node_entries(graph, "story")
    contrast_pairs = _node_entries(graph, "contrast_pair")
    thinking_models = _node_entries(graph, "thinking_model")

    beliefs.sort(key=_conviction_score, reverse=True)
    stories.sort(key=lambda s: s.get("engagement", 0) or 0, reverse=True)
    thinking_models.sort(key=lambda m: m.get("priority", 0) or 0, reverse=True)

    cast, scenes = top_cast_and_scenes(graph)
    milestones = top_milestones(graph)
    top_beliefs = beliefs[:15]
    topic_neighbors: dict[str, list[dict]] = neighbors_for_topic(graph, topic) if topic else {}

    style_rules = get_style_rules_for_platform(graph, platform)
    vocab = get_vocabulary_rules(graph)
    personality_card = get_personality_card(graph)

    traceability: dict[str, Any] = {
        "belief_nodes": [
            {"node_id": b.get("node_id", ""), "topic": b.get("topic", ""),
             "stance": (b.get("stance") or "")[:80],
             "conviction": _conviction_score(b)}
            for b in beliefs
        ],
        "story_nodes": [{"node_id": s.get("node_id", ""), "title": (s.get("title") or "")[:80]} for s in stories],
        "contrast_pairs": [{"node_id": c.get("node_id", ""), "left": c.get("left", ""),
                            "right": c.get("right", "")} for c in contrast_pairs],
        "thinking_models": [{"node_id": m.get("node_id", ""), "name": m.get("name", "")} for m in thinking_models],
        "cast_nodes": [{"node_id": c.get("node_id", ""), "name": c.get("name") or c.get("label", "")} for c in cast],
        "scene_nodes": [{"node_id": s.get("node_id", ""), "name": s.get("name") or s.get("label", "")} for s in scenes],
        "milestone_nodes": [{"node_id": m.get("node_id", ""), "label": m.get("label") or m.get("title", "")} for m in milestones],
        "top_beliefs_by_conviction": [b.get("node_id", "") for b in top_beliefs],
        "style_rule_count": len(style_rules),
        "vocabulary_phrases_used": len(vocab.get("phrases_used", [])),
        "vocabulary_phrases_never": len(vocab.get("phrases_never", [])),
    }

    return {
        "beliefs": beliefs,
        "stories": stories,
        "style_rules": style_rules,
        "contrast_pairs": contrast_pairs,
        "thinking_models": thinking_models,
        "vocabulary": vocab,
        "personality_card": personality_card,
        "platform": platform,
        "cast": cast,
        "scenes": scenes,
        "milestones": milestones,
        "top_beliefs_by_conviction": top_beliefs,
        "topic_neighbors": topic_neighbors,
        "traceability": traceability,
    }
