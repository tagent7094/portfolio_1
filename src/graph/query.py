"""Query the knowledge graph for generation context.

Changes from original:
- Issue #8:  Uses shared normalize_topic() from builder (no split-brain)
- Issue #20: Fixed get_stories_for_beliefs() to use SUPPORTS and BEST_FOR correctly
- Issue #29: Added get_contrast_pairs() so contrast pairs are actually queryable
- Removed redundant _TOPIC_SYNONYMS dict (uses builder.normalize_topic)
- Added get_stories_for_topic() for direct topic→story lookup
- Improved fallback behavior with logging
"""

from __future__ import annotations

import sys

import networkx as nx

from .builder import normalize_topic, _tokenize


def get_beliefs_for_topic(graph: nx.DiGraph, topic: str) -> list[dict]:
    """Get all beliefs related to a topic, sorted by confidence.

    Uses the shared normalize_topic() for consistent bucket matching.
    """
    topic_buckets = normalize_topic(topic)
    topic_tokens = _tokenize(topic)
    beliefs = []
    seen_ids = set()

    for node_id, data in graph.nodes(data=True):
        if data.get("node_type") != "belief":
            continue

        # Strategy 1: topic bucket overlap (highest quality match)
        node_buckets = set(data.get("topic_buckets", []))
        if not node_buckets:
            node_buckets = normalize_topic(data.get("topic", ""))

        bucket_match = bool(topic_buckets & node_buckets)

        # Strategy 2: keyword overlap on stance + topic
        node_text = f"{data.get('topic', '')} {data.get('stance', '')}".lower()
        node_tokens = _tokenize(node_text)
        overlap = len(topic_tokens & node_tokens)
        keyword_match = overlap >= 2

        if bucket_match or keyword_match:
            if node_id not in seen_ids:
                beliefs.append({**data, "node_id": node_id, "_match_strength": int(bucket_match) * 10 + overlap})
                seen_ids.add(node_id)

    if not beliefs:
        # Fallback: top beliefs by confidence
        all_beliefs = [{**d, "node_id": n} for n, d in graph.nodes(data=True)
                       if d.get("node_type") == "belief"]
        result = sorted(all_beliefs, key=lambda b: b.get("confidence", 0), reverse=True)[:5]
        _log(f"get_beliefs_for_topic({topic!r}) → 0 matches, fallback {len(result)}")
        return result

    # Sort by match strength first, then confidence
    result = sorted(beliefs, key=lambda b: (b.get("_match_strength", 0), b.get("confidence", 0)), reverse=True)
    _log(f"get_beliefs_for_topic({topic!r}) → {len(result)} beliefs")
    return result


def get_stories_for_beliefs(graph: nx.DiGraph, belief_ids: list[str]) -> list[dict]:
    """Get stories that support given beliefs via SUPPORTS or BEST_FOR edges."""
    story_ids = set()
    for belief_id in belief_ids:
        if not belief_id or belief_id not in graph:
            continue
        for pred in graph.predecessors(belief_id):
            if pred not in graph:
                continue
            pred_data = graph.nodes[pred]
            if pred_data.get("node_type") != "story":
                continue
            edge_data = graph.edges[pred, belief_id]
            if edge_data.get("edge_type") in ("SUPPORTS", "BEST_FOR"):
                story_ids.add(pred)

    stories = [{**graph.nodes[sid], "node_id": sid} for sid in story_ids if sid in graph.nodes]

    if not stories:
        all_stories = [{**d, "node_id": n} for n, d in graph.nodes(data=True)
                       if d.get("node_type") == "story"]
        # Sort by engagement (now populated), then virality potential
        vp_order = {"high": 3, "medium": 2, "low": 1}
        result = sorted(all_stories,
                        key=lambda s: (s.get("engagement", 0), vp_order.get(s.get("virality_potential", ""), 0)),
                        reverse=True)[:3]
        _log(f"get_stories_for_beliefs({len(belief_ids)} beliefs) → 0 direct, fallback {len(result)}")
        return result

    result = sorted(stories, key=lambda s: s.get("engagement", 0), reverse=True)
    _log(f"get_stories_for_beliefs({len(belief_ids)} beliefs) → {len(result)} stories")
    return result


def get_stories_for_topic(graph: nx.DiGraph, topic: str) -> list[dict]:
    """Get stories directly relevant to a topic via best_used_for matching."""
    topic_buckets = normalize_topic(topic)
    stories = []

    for node_id, data in graph.nodes(data=True):
        if data.get("node_type") != "story":
            continue
        story_buckets = set()
        for buf in data.get("best_used_for", []):
            story_buckets.update(normalize_topic(buf))

        if topic_buckets & story_buckets:
            stories.append({**data, "node_id": node_id})

    return sorted(stories, key=lambda s: s.get("engagement", 0), reverse=True)


def get_style_rules_for_platform(graph: nx.DiGraph, platform: str) -> list[dict]:
    """Get all style rules applicable to a platform."""
    rules = []
    for node_id, data in graph.nodes(data=True):
        if data.get("node_type") != "style_rule":
            continue
        rule_platform = data.get("platform", "universal")
        if rule_platform in ("universal", platform):
            rules.append({**data, "node_id": node_id})
    _log(f"get_style_rules_for_platform({platform!r}) → {len(rules)} rules")
    return rules


def get_contrast_pairs(graph: nx.DiGraph, topic: str | None = None) -> list[dict]:
    """Get contrast pairs, optionally filtered by topic.

    Issue #29: Contrast pairs were previously invisible to generation.
    """
    pairs = []
    topic_buckets = normalize_topic(topic) if topic else set()

    for node_id, data in graph.nodes(data=True):
        if data.get("node_type") != "contrast_pair":
            continue

        if not topic:
            pairs.append({**data, "node_id": node_id})
            continue

        # Check if any connected story is in the topic
        connected_stories = [
            pred for pred in graph.predecessors(node_id)
            if graph.nodes.get(pred, {}).get("node_type") == "story"
            and graph.edges[pred, node_id].get("edge_type") == "ILLUMINATES"
        ]

        # Check story topics
        for sid in connected_stories:
            story_data = graph.nodes[sid]
            story_buckets = set()
            for buf in story_data.get("best_used_for", []):
                story_buckets.update(normalize_topic(buf))
            if topic_buckets & story_buckets:
                pairs.append({**data, "node_id": node_id})
                break
        else:
            # Keyword match on contrast description
            desc = f"{data.get('left', '')} {data.get('right', '')} {data.get('description', '')}"
            desc_tokens = _tokenize(desc)
            topic_tokens = _tokenize(topic)
            if len(desc_tokens & topic_tokens) >= 2:
                pairs.append({**data, "node_id": node_id})

    _log(f"get_contrast_pairs({topic!r}) → {len(pairs)} pairs")
    return pairs


def get_rhetorical_moves_for_register(graph: nx.DiGraph, register: str) -> list[dict]:
    """Get rhetorical moves matching an emotional register."""
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
    _log(f"get_vocabulary_rules() → {len(result['phrases_used'])} use, {len(result['phrases_never'])} never")
    return result


def get_personality_card(graph: nx.DiGraph) -> str:
    """Get the natural language personality summary (sanitized)."""
    card = graph.graph.get("personality_card", "")
    _log(f"get_personality_card() → {len(card)} chars")
    return card


def get_thinking_models(graph: nx.DiGraph, topic: str | None = None) -> list[dict]:
    """Get thinking models, optionally filtered by topic relevance."""
    models = []
    topic_tokens = _tokenize(topic) if topic else set()
    topic_lower = topic.lower().strip() if topic else ""

    for node_id, data in graph.nodes(data=True):
        if data.get("node_type") != "thinking_model":
            continue
        if not topic:
            models.append({**data, "node_id": node_id})
            continue

        model_text = f"{data.get('name', '')} {data.get('description', '')}".lower()
        model_tokens = _tokenize(model_text)

        # Token overlap (standard)
        token_match = len(topic_tokens & model_tokens) >= 2

        # Substring match for short terms (e.g. "AI" in description)
        substring_match = topic_lower in model_text

        # Check topic words individually (handles "AI Leadership" where "AI" is 2 chars)
        word_match = any(w.lower() in model_text for w in (topic or "").split() if len(w) >= 2)

        if token_match or substring_match or word_match:
            models.append({**data, "node_id": node_id})

    return sorted(models, key=lambda m: m.get("priority", 0), reverse=True)


def get_full_context(graph: nx.DiGraph, topic: str, platform: str) -> dict:
    """Assemble complete generation context including contrast pairs."""
    _log(f"get_full_context(topic={topic!r}, platform={platform!r})")

    beliefs = get_beliefs_for_topic(graph, topic)
    belief_ids = [b.get("node_id", "") for b in beliefs]
    stories = get_stories_for_beliefs(graph, belief_ids)
    style_rules = get_style_rules_for_platform(graph, platform)
    contrast_pairs = get_contrast_pairs(graph, topic)
    thinking_models = get_thinking_models(graph, topic)
    vocab = get_vocabulary_rules(graph)
    personality_card = get_personality_card(graph)

    traceability = {
        "belief_nodes": [{"node_id": b.get("node_id", ""), "topic": b.get("topic", ""),
                          "stance": b.get("stance", "")[:80]} for b in beliefs],
        "story_nodes": [{"node_id": s.get("node_id", ""), "title": s.get("title", "")[:80]} for s in stories],
        "contrast_pairs": [{"node_id": c.get("node_id", ""), "left": c.get("left", ""),
                            "right": c.get("right", "")} for c in contrast_pairs],
        "thinking_models": [{"node_id": m.get("node_id", ""), "name": m.get("name", "")} for m in thinking_models],
        "style_rule_count": len(style_rules),
        "vocabulary_phrases_used": len(vocab.get("phrases_used", [])),
        "vocabulary_phrases_never": len(vocab.get("phrases_never", [])),
    }

    _log(f"Context: {len(beliefs)}B {len(stories)}S {len(contrast_pairs)}CP "
         f"{len(thinking_models)}TM {len(style_rules)}R")

    return {
        "beliefs": beliefs,
        "stories": stories,
        "style_rules": style_rules,
        "contrast_pairs": contrast_pairs,
        "thinking_models": thinking_models,
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
    """Merge founder graph context with viral graph context."""
    _log(f"get_merged_context(topic={topic!r}, platform={platform!r}, creativity={creativity})")

    context = get_full_context(founder_graph, topic, platform)

    viral_context = {}
    viral_context_text = ""
    if viral_graph is not None and viral_graph.number_of_nodes() > 0:
        from .viral_query import get_viral_context_for_topic, format_viral_context_for_prompt
        viral_context = get_viral_context_for_topic(viral_graph, topic, creativity)
        viral_context_text = format_viral_context_for_prompt(viral_context, creativity)

    from ..generation.creativity import build_creativity_instructions
    creativity_block = build_creativity_instructions(creativity, viral_context_text)

    context["viral_context"] = viral_context
    context["viral_context_block"] = creativity_block
    context["creativity"] = creativity

    return context


def _log(msg: str):
    print(f"\033[33m[GraphQuery]\033[0m {msg}", file=sys.stderr, flush=True)