"""Query the knowledge graph for generation context."""

from __future__ import annotations

import sys

import networkx as nx


_TOPIC_SYNONYMS = {
    "ai": {"ai", "artificial intelligence", "automation", "ai_automation", "ai_augmentation", "machine learning"},
    "hiring": {"hiring", "talent", "recruiting", "culture", "hiring & talent"},
    "leadership": {"leadership", "management", "ceo", "founder"},
    "fundraising": {"fundraising", "investors", "capital", "fundraising_and_investors", "series"},
    "industry": {"industry", "market", "enterprise", "saas", "building_companies"},
    "sales": {"sales", "revenue", "deals", "closing"},
    "personal": {"personal", "growth", "learning", "journey"},
    "bias": {"bias", "accent", "human connection", "discrimination", "diversity"},
}


def _topic_keywords(topic: str) -> set[str]:
    """Expand a topic into a set of matchable keywords."""
    words = set()
    topic_lower = topic.lower()
    # Add raw words (3+ chars)
    for w in topic_lower.replace("_", " ").replace("|", " ").replace("/", " ").split():
        if len(w) >= 3:
            words.add(w)
    # Expand synonyms
    for key, synonyms in _TOPIC_SYNONYMS.items():
        if any(s in topic_lower for s in synonyms) or key in topic_lower:
            words.update(synonyms)
    return words


def get_beliefs_for_topic(graph: nx.DiGraph, topic: str) -> list[dict]:
    """Get all beliefs related to a topic, sorted by confidence.

    Uses keyword expansion and synonym matching for broader coverage.
    """
    topic_kws = _topic_keywords(topic)
    beliefs = []

    for node_id, data in graph.nodes(data=True):
        if data.get("node_type") != "belief":
            continue
        node_topic = data.get("topic", "").lower()
        node_stance = data.get("stance", "").lower()

        # Direct substring match (original behavior)
        if topic.lower() in node_topic or node_topic in topic.lower():
            beliefs.append({**data, "node_id": node_id})
            continue

        # Keyword overlap match
        node_kws = _topic_keywords(node_topic)
        overlap = topic_kws & node_kws
        if len(overlap) >= 1:
            beliefs.append({**data, "node_id": node_id})
            continue

        # Stance keyword match (check if topic words appear in the belief stance)
        stance_words = set(w for w in node_stance.split() if len(w) >= 4)
        if len(topic_kws & stance_words) >= 2:
            beliefs.append({**data, "node_id": node_id})

    if not beliefs:
        all_beliefs = [{**d, "node_id": n} for n, d in graph.nodes(data=True) if d.get("node_type") == "belief"]
        result = sorted(all_beliefs, key=lambda b: b.get("confidence", 0), reverse=True)[:5]
        print(f"\033[33m[GraphQuery]\033[0m get_beliefs_for_topic(topic={topic!r}) → 0 direct matches, using {len(result)} core beliefs as fallback", file=sys.stderr, flush=True)
        return result

    result = sorted(beliefs, key=lambda b: b.get("confidence", 0), reverse=True)
    print(f"\033[33m[GraphQuery]\033[0m get_beliefs_for_topic(topic={topic!r}) → {len(result)} beliefs", file=sys.stderr, flush=True)
    return result


def get_stories_for_beliefs(graph: nx.DiGraph, belief_ids: list[str]) -> list[dict]:
    """Get stories that support given beliefs, sorted by engagement."""
    story_ids = set()
    for belief_id in belief_ids:
        if not belief_id or belief_id not in graph:
            continue
        for pred in graph.predecessors(belief_id):
            edge_data = graph.edges[pred, belief_id]
            if edge_data.get("edge_type") in ("SUPPORTS", "BEST_FOR"):
                story_ids.add(pred)
    stories = [{**graph.nodes[sid], "node_id": sid} for sid in story_ids if sid in graph.nodes]
    if not stories:
        all_stories = [{**d, "node_id": n} for n, d in graph.nodes(data=True) if d.get("node_type") == "story"]
        result = sorted(all_stories, key=lambda s: s.get("engagement", 0), reverse=True)[:3]
        print(f"\033[33m[GraphQuery]\033[0m get_stories_for_beliefs(belief_ids={len(belief_ids)}) → 0 direct matches, using {len(result)} core stories as fallback", file=sys.stderr, flush=True)
        return result

    result = sorted(stories, key=lambda s: s.get("engagement", 0), reverse=True)
    print(f"\033[33m[GraphQuery]\033[0m get_stories_for_beliefs(belief_ids={len(belief_ids)}) → {len(result)} stories", file=sys.stderr, flush=True)
    return result


def get_style_rules_for_platform(graph: nx.DiGraph, platform: str) -> list[dict]:
    """Get all style rules applicable to a platform."""
    rules = []
    for node_id, data in graph.nodes(data=True):
        if data.get("node_type") != "style_rule":
            continue
        rule_platform = data.get("platform", "universal")
        if rule_platform in ("universal", platform):
            rules.append({**data, "node_id": node_id})
    print(f"\033[33m[GraphQuery]\033[0m get_style_rules_for_platform(platform={platform!r}) → {len(rules)} rules", file=sys.stderr, flush=True)
    return rules


def get_rhetorical_moves_for_register(graph: nx.DiGraph, register: str) -> list[dict]:
    """Get rhetorical moves triggered by an emotional register."""
    moves = []
    for _, data in graph.nodes(data=True):
        if data.get("node_type") != "style_rule":
            continue
        if data.get("rule_type") == "rhetorical_move":
            moves.append(data)
    return moves


def get_vocabulary_rules(graph: nx.DiGraph) -> dict:
    """Get use/never-use word lists."""
    if "vocabulary" in graph.nodes:
        data = graph.nodes["vocabulary"]
        result = {
            "phrases_used": data.get("phrases_used", []),
            "phrases_never": data.get("phrases_never", []),
            "pronoun_rules": data.get("pronoun_rules", {}),
        }
    else:
        result = {"phrases_used": [], "phrases_never": [], "pronoun_rules": {}}
    print(f"\033[33m[GraphQuery]\033[0m get_vocabulary_rules() → {len(result.get('phrases_used', []))} use, {len(result.get('phrases_never', []))} never", file=sys.stderr, flush=True)
    return result


def get_personality_card(graph: nx.DiGraph) -> str:
    """Get the natural language personality summary."""
    card = graph.graph.get("personality_card", "")
    print(f"\033[33m[GraphQuery]\033[0m get_personality_card() → {len(card)} chars", file=sys.stderr, flush=True)
    return card


def get_full_context(graph: nx.DiGraph, topic: str, platform: str) -> dict:
    """Assemble complete generation context."""
    print(f"\033[33m[GraphQuery]\033[0m \033[1mget_full_context(topic={topic!r}, platform={platform!r})\033[0m", file=sys.stderr, flush=True)
    beliefs = get_beliefs_for_topic(graph, topic)
    belief_ids = [b.get("node_id", "") for b in beliefs]
    stories = get_stories_for_beliefs(graph, belief_ids)
    style_rules = get_style_rules_for_platform(graph, platform)
    vocab = get_vocabulary_rules(graph)
    personality_card = get_personality_card(graph)

    # Build traceability metadata
    traceability = {
        "belief_nodes": [{"node_id": b.get("node_id", ""), "topic": b.get("topic", ""), "stance": b.get("stance", "")[:80]} for b in beliefs],
        "story_nodes": [{"node_id": s.get("node_id", ""), "title": s.get("title", "")[:80]} for s in stories],
        "style_rule_nodes": [{"node_id": r.get("node_id", ""), "rule_type": r.get("rule_type", ""), "description": r.get("description", "")[:80]} for r in style_rules],
        "vocabulary_phrases_used": len(vocab.get("phrases_used", [])),
        "vocabulary_phrases_never": len(vocab.get("phrases_never", [])),
    }
    print(f"\033[33m[GraphQuery]\033[0m Traceability: {len(traceability['belief_nodes'])} beliefs, {len(traceability['story_nodes'])} stories, {len(traceability['style_rule_nodes'])} style rules", file=sys.stderr, flush=True)

    return {
        "beliefs": beliefs,
        "stories": stories,
        "style_rules": style_rules,
        "vocabulary": vocab,
        "personality_card": personality_card,
        "topic": topic,
        "platform": platform,
        "traceability": traceability,
    }


def get_merged_context(
    founder_graph: nx.DiGraph,
    viral_graph: nx.DiGraph | None,
    topic: str,
    platform: str,
    creativity: float = 0.5,
) -> dict:
    """Merge founder graph context with viral graph context.

    Returns the standard context dict with additional viral_context and creativity keys.
    """
    print(f"\033[33m[GraphQuery]\033[0m \033[1mget_merged_context(topic={topic!r}, platform={platform!r}, creativity={creativity})\033[0m", file=sys.stderr, flush=True)
    # Founder context (always)
    context = get_full_context(founder_graph, topic, platform)

    # Viral context (if available)
    viral_context = {}
    viral_context_text = ""
    if viral_graph is not None and viral_graph.number_of_nodes() > 0:
        from .viral_query import get_viral_context_for_topic, format_viral_context_for_prompt
        viral_context = get_viral_context_for_topic(viral_graph, topic, creativity)
        viral_context_text = format_viral_context_for_prompt(viral_context, creativity)

    # Creativity instructions
    from ..generation.creativity import build_creativity_instructions
    creativity_block = build_creativity_instructions(creativity, viral_context_text)

    context["viral_context"] = viral_context
    context["viral_context_block"] = creativity_block
    context["creativity"] = creativity

    return context
