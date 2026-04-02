"""Build the knowledge graph from extracted data."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import asdict

import networkx as nx

from .schema import (
    BeliefNode,
    CategoryNode,
    ContrastPairNode,
    FounderNode,
    StoryNode,
    StyleRuleNode,
    ThinkingModelNode,
    VocabularyNode,
    CATEGORY_HUBS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stopwords & topic normalisation
# ---------------------------------------------------------------------------

STOPWORDS = frozenset(
    "a an the is are was were be been being have has had do does did will would "
    "shall should may might can could must need dare ought i me my we our you your "
    "he him his she her it its they them their this that these those am not no nor "
    "so if or but and for at by to in on of from with as into about between through "
    "during before after above below up down out off over under again further then "
    "once here there when where why how all each every both few more most other some "
    "such than too very just also now only still already even much really well back "
    "still going get got like make made one two three also way what which who whom "
    "been because while".split()
)

# Map related terms to canonical topic buckets
TOPIC_SYNONYMS: dict[str, str] = {
    "ai": "technology",
    "automation": "technology",
    "artificial intelligence": "technology",
    "machine learning": "technology",
    "ml": "technology",
    "tech": "technology",
    "ai_automation": "technology",
    "hiring": "talent",
    "talent": "talent",
    "recruitment": "talent",
    "team": "talent",
    "people": "talent",
    "culture": "talent",
    "cultural fit": "talent",
    "fundraising": "business",
    "funding": "business",
    "vc": "business",
    "investor": "business",
    "venture capital": "business",
    "investment": "business",
    "sales": "business",
    "enterprise": "business",
    "revenue": "business",
    "growth": "business",
    "scaling": "business",
    "scale": "business",
    "leadership": "leadership",
    "management": "leadership",
    "founder": "leadership",
    "ceo": "leadership",
    "executive": "leadership",
    "decision": "leadership",
    "strategy": "leadership",
    "vision": "leadership",
    "industry": "industry",
    "market": "industry",
    "competition": "industry",
    "product": "product",
    "innovation": "product",
    "building": "product",
    "engineering": "product",
    "personal": "personal",
    "identity": "personal",
    "accent": "personal",
    "bias": "personal",
    "diversity": "personal",
    "inclusion": "personal",
    "empathy": "personal",
    "resilience": "personal",
    "communication": "communication",
    "storytelling": "communication",
    "narrative": "communication",
    "writing": "communication",
}

# Emotional register → style rule_type affinities
REGISTER_STYLE_MAP: dict[str, list[str]] = {
    "controlled_anger": ["rhetorical_move", "punctuation", "rhythm"],
    "quiet_authority": ["opening", "closing", "rhythm"],
    "earned_vulnerability": ["rhetorical_move", "opening"],
    "generosity": ["closing", "vocabulary"],
    "paranoid_optimist": ["rhetorical_move", "rhythm", "opening"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set[str]:
    """Tokenize text into lowercase keyword set, stripping stopwords."""
    words = re.findall(r"[a-z][a-z']+", text.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 2}


def _keyword_overlap(text_a: str, text_b: str) -> int:
    """Return count of shared meaningful keywords between two texts."""
    return len(_tokenize(text_a) & _tokenize(text_b))


def _normalize_topic(topic: str) -> str:
    """Map a topic string to its canonical bucket."""
    t = topic.lower().strip()
    if t in TOPIC_SYNONYMS:
        return TOPIC_SYNONYMS[t]
    # Try each word
    for word in t.split("_"):
        if word in TOPIC_SYNONYMS:
            return TOPIC_SYNONYMS[word]
    return t


def _ensure_list(val) -> list:
    """Coerce a value to a list of strings, handling None/str/dict."""
    if val is None:
        return []
    if isinstance(val, str):
        return [val]
    if isinstance(val, list):
        return [str(x) for x in val]
    return [str(val)]


def _ensure_str(val) -> str:
    """Coerce a value to a string, handling None."""
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    return str(val)


def _text_for_story(story_data: dict) -> str:
    """Combine all textual fields of a story for matching."""
    parts = [
        _ensure_str(story_data.get("title", "")),
        _ensure_str(story_data.get("summary", "")),
        " ".join(_ensure_list(story_data.get("best_used_for"))),
        " ".join(_ensure_list(story_data.get("key_quotes"))),
    ]
    return " ".join(parts)


def _text_for_belief(belief_data: dict) -> str:
    """Combine textual fields of a belief for matching."""
    parts = [
        _ensure_str(belief_data.get("topic", "")),
        _ensure_str(belief_data.get("stance", "")),
        _ensure_str(belief_data.get("opposes", "")),
    ]
    return " ".join(parts)


def _text_for_model(model_data: dict) -> str:
    """Combine textual fields of a thinking model."""
    return f"{_ensure_str(model_data.get('name', ''))} {_ensure_str(model_data.get('description', ''))}"


def _text_for_style(style_data: dict) -> str:
    """Combine textual fields of a style rule."""
    parts = [
        _ensure_str(style_data.get("description", "")),
        " ".join(_ensure_list(style_data.get("examples"))),
        _ensure_str(style_data.get("anti_pattern", "")),
    ]
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_graph(extracted_data: dict, existing_graph: nx.DiGraph | None = None) -> nx.DiGraph:
    """Build or merge a knowledge graph from extracted data.

    Args:
        extracted_data: dict with keys: beliefs, stories, style_rules, thinking_models, vocabulary, personality_card
        existing_graph: optional existing graph to merge into
    """
    graph = existing_graph if existing_graph is not None else nx.DiGraph()

    # ---- Founder node ----
    founder_label = "Founder"
    pc = extracted_data.get("personality_card", "")
    if pc:
        # Try to extract name from personality card
        for line in pc.split("\n")[:5]:
            if "you are" in line.lower() or "sharath" in line.lower():
                founder_label = "Sharath"
                break

    if "founder" not in graph:
        graph.add_node("founder", node_type="founder", label=founder_label, description="Central founder node")

    # ---- Category hub nodes ----
    for cat_id, cat_info in CATEGORY_HUBS.items():
        if cat_id not in graph:
            graph.add_node(cat_id, node_type="category", label=cat_info["label"], category_type=cat_info["category_type"])
        if not graph.has_edge("founder", cat_id):
            graph.add_edge("founder", cat_id, edge_type="HAS_CATEGORY")

    # ---- Add belief nodes ----
    for belief in extracted_data.get("beliefs", []):
        node_id = f"belief_{belief.get('id', 'unknown')}"
        if node_id in graph:
            existing = graph.nodes[node_id]
            evidence = existing.get("evidence_quotes", [])
            new_quote = belief.get("evidence_quote", "")
            if new_quote and new_quote not in evidence:
                evidence.append(new_quote)
            existing["evidence_quotes"] = evidence
        else:
            node = BeliefNode(
                id=node_id,
                topic=belief.get("topic", "general"),
                stance=belief.get("stance", ""),
                confidence=belief.get("confidence", 0.5),
                evidence_quotes=[belief.get("evidence_quote", "")] if belief.get("evidence_quote") else [],
                opposes=belief.get("opposes"),
            )
            graph.add_node(node_id, **asdict(node), node_type="belief")
        # Connect to category hub
        if not graph.has_edge("cat_beliefs", node_id):
            graph.add_edge("cat_beliefs", node_id, edge_type="CONTAINS")

    # ---- Add story nodes ----
    for story in extracted_data.get("stories", []):
        node_id = f"story_{story.get('id', 'unknown')}"
        if node_id not in graph:
            node = StoryNode(
                id=node_id,
                title=story.get("title", ""),
                summary=story.get("summary", ""),
                emotional_register=story.get("emotional_register", "quiet_authority"),
                contrast_pair=story.get("contrast_pair"),
                best_used_for=story.get("best_used_for", []),
                key_quotes=story.get("key_quotes", []),
                virality_potential=story.get("virality_potential", "medium"),
            )
            graph.add_node(node_id, **asdict(node), node_type="story")
        if not graph.has_edge("cat_stories", node_id):
            graph.add_edge("cat_stories", node_id, edge_type="CONTAINS")

    # ---- Add style rule nodes ----
    for rule in extracted_data.get("style_rules", []):
        node_id = f"style_{rule.get('id', 'unknown')}"
        if node_id not in graph:
            node = StyleRuleNode(
                id=node_id,
                rule_type=rule.get("rule_type", ""),
                description=rule.get("description", ""),
                examples=rule.get("examples", []),
                anti_pattern=rule.get("anti_pattern"),
                platform=rule.get("platform", "universal"),
            )
            graph.add_node(node_id, **asdict(node), node_type="style_rule")
        if not graph.has_edge("cat_style", node_id):
            graph.add_edge("cat_style", node_id, edge_type="CONTAINS")

    # ---- Add thinking model nodes ----
    for model in extracted_data.get("thinking_models", []):
        node_id = f"model_{model.get('id', 'unknown')}"
        if node_id not in graph:
            node = ThinkingModelNode(
                id=node_id,
                name=model.get("name", ""),
                description=model.get("description", ""),
                priority=model.get("priority", 0),
            )
            graph.add_node(node_id, **asdict(node), node_type="thinking_model")
        if not graph.has_edge("cat_models", node_id):
            graph.add_edge("cat_models", node_id, edge_type="CONTAINS")

    # ---- Add vocabulary node ----
    vocab = extracted_data.get("vocabulary", {})
    if vocab:
        node = VocabularyNode(
            phrases_used=vocab.get("phrases_used", []),
            phrases_never=vocab.get("phrases_never", []),
            pronoun_rules=vocab.get("pronoun_rules", {}),
        )
        graph.add_node("vocabulary", **asdict(node), node_type="vocabulary")
        if not graph.has_edge("cat_vocabulary", "vocabulary"):
            graph.add_edge("cat_vocabulary", "vocabulary", edge_type="CONTAINS")

    # Store personality card as graph attribute
    if extracted_data.get("personality_card"):
        graph.graph["personality_card"] = extracted_data["personality_card"]

    # Build cross-type edges
    _build_edges(graph)

    logger.info(
        "Graph built: %d nodes, %d edges",
        graph.number_of_nodes(),
        graph.number_of_edges(),
    )
    return graph


def _build_edges(graph: nx.DiGraph):
    """Create rich cross-type edges using multi-strategy matching."""
    beliefs = [(n, graph.nodes[n]) for n in graph if graph.nodes[n].get("node_type") == "belief"]
    stories = [(n, graph.nodes[n]) for n in graph if graph.nodes[n].get("node_type") == "story"]
    models = [(n, graph.nodes[n]) for n in graph if graph.nodes[n].get("node_type") == "thinking_model"]
    styles = [(n, graph.nodes[n]) for n in graph if graph.nodes[n].get("node_type") == "style_rule"]
    has_vocab = "vocabulary" in graph

    # ---- A. Story → Belief (SUPPORTS) ----
    # Use keyword overlap + topic normalisation
    for story_id, story in stories:
        story_text = _text_for_story(story)
        story_tokens = _tokenize(story_text)
        story_topics = set()
        for bf in story.get("best_used_for", []):
            for word in _tokenize(bf):
                if word in TOPIC_SYNONYMS:
                    story_topics.add(TOPIC_SYNONYMS[word])
            story_topics.add(_normalize_topic(bf))

        for belief_id, belief in beliefs:
            belief_topic_norm = _normalize_topic(belief.get("topic", ""))
            belief_text = _text_for_belief(belief)
            belief_tokens = _tokenize(belief_text)

            # Strategy 1: normalised topic match
            topic_match = belief_topic_norm in story_topics

            # Strategy 2: keyword overlap (need 3+ shared words)
            overlap = len(story_tokens & belief_tokens)
            keyword_match = overlap >= 3

            if topic_match or keyword_match:
                if not graph.has_edge(story_id, belief_id):
                    graph.add_edge(story_id, belief_id, edge_type="SUPPORTS", strength=overlap)

    # ---- B. Belief → Belief (CONTRADICTS / RELATED) ----
    topic_groups: dict[str, list[str]] = defaultdict(list)
    for belief_id, belief in beliefs:
        topic_groups[_normalize_topic(belief.get("topic", ""))].append(belief_id)

    # RELATED: beliefs in same topic cluster
    for topic, group in topic_groups.items():
        if len(group) > 1:
            for i, b1 in enumerate(group):
                for b2 in group[i + 1:]:
                    if not graph.has_edge(b1, b2) and not graph.has_edge(b2, b1):
                        graph.add_edge(b1, b2, edge_type="RELATED")

    # CONTRADICTS: check opposes field against other belief stances
    for belief_id, belief in beliefs:
        opposes = belief.get("opposes", "") or ""
        if not opposes or len(opposes) < 10:
            continue
        opposes_tokens = _tokenize(opposes)
        for other_id, other in beliefs:
            if other_id == belief_id:
                continue
            other_stance = other.get("stance", "")
            overlap = len(opposes_tokens & _tokenize(other_stance))
            if overlap >= 3 and not graph.has_edge(belief_id, other_id):
                graph.add_edge(belief_id, other_id, edge_type="CONTRADICTS")

    # ---- C. Story → Style Rule (USES_STYLE) ----
    for story_id, story in stories:
        register = story.get("emotional_register", "")
        story_text = _text_for_story(story)
        affinity_types = REGISTER_STYLE_MAP.get(register, [])

        for style_id, style in styles:
            rule_type = style.get("rule_type", "")

            # Strategy 1: register → rule_type affinity
            register_match = rule_type in affinity_types

            # Strategy 2: keyword overlap between story text and style description
            style_text = _text_for_style(style)
            overlap = _keyword_overlap(story_text, style_text)
            keyword_match = overlap >= 3

            if register_match or keyword_match:
                if not graph.has_edge(story_id, style_id):
                    graph.add_edge(story_id, style_id, edge_type="USES_STYLE")

    # ---- D. Thinking Model → Belief (INFORMS) ----
    for model_id, model in models:
        model_text = _text_for_model(model)
        model_tokens = _tokenize(model_text)

        for belief_id, belief in beliefs:
            belief_text = _text_for_belief(belief)
            belief_tokens = _tokenize(belief_text)
            overlap = len(model_tokens & belief_tokens)
            if overlap >= 2:
                if not graph.has_edge(model_id, belief_id):
                    graph.add_edge(model_id, belief_id, edge_type="INFORMS")

    # ---- E. Story → Thinking Model (DEMONSTRATES) ----
    for story_id, story in stories:
        story_text = _text_for_story(story)
        story_tokens = _tokenize(story_text)

        for model_id, model in models:
            model_name = model.get("name", "").lower()
            model_tokens = _tokenize(_text_for_model(model))

            # Strategy 1: model name appears in story text
            name_match = model_name and model_name in story_text.lower()

            # Strategy 2: keyword overlap (need 3+)
            overlap = len(story_tokens & model_tokens)
            keyword_match = overlap >= 3

            if name_match or keyword_match:
                if not graph.has_edge(story_id, model_id):
                    graph.add_edge(story_id, model_id, edge_type="DEMONSTRATES")

    # ---- F. Vocabulary → Style Rules (CONSTRAINS) ----
    if has_vocab:
        for style_id, style in styles:
            if style.get("rule_type") == "vocabulary":
                if not graph.has_edge("vocabulary", style_id):
                    graph.add_edge("vocabulary", style_id, edge_type="CONSTRAINS")

    # ---- G. Contrast Pair Nodes (ILLUMINATES) ----
    seen_pairs: dict[str, str] = {}
    for story_id, story in stories:
        cp = story.get("contrast_pair")
        if not cp:
            continue

        # Normalise the contrast pair key
        cp_key = cp.strip().lower()
        if cp_key in seen_pairs:
            cp_node_id = seen_pairs[cp_key]
        else:
            # Create a new contrast pair node
            cp_clean = re.sub(r"[^a-z0-9 ]", "", cp_key)
            cp_node_id = f"contrast_{cp_clean.replace(' ', '_')[:50]}"
            if cp_node_id not in graph:
                parts = re.split(r"\s+vs\.?\s+", cp, flags=re.IGNORECASE)
                left = parts[0].strip() if len(parts) > 0 else cp
                right = parts[1].strip() if len(parts) > 1 else ""
                graph.add_node(
                    cp_node_id,
                    node_type="contrast_pair",
                    left=left,
                    right=right,
                    description=cp,
                    id=cp_node_id,
                    label=cp[:60],
                )
                # Connect to stories category
                if not graph.has_edge("cat_stories", cp_node_id):
                    graph.add_edge("cat_stories", cp_node_id, edge_type="CONTAINS")
            seen_pairs[cp_key] = cp_node_id

        # Connect story → contrast pair
        if not graph.has_edge(story_id, cp_node_id):
            graph.add_edge(story_id, cp_node_id, edge_type="ILLUMINATES")

    # ---- H. Thinking Model → Style Rule ----
    # Models about communication / reasoning connect to rhetorical style rules
    for model_id, model in models:
        model_text = _text_for_model(model)
        for style_id, style in styles:
            if style.get("rule_type") in ("rhetorical_move", "rhythm"):
                style_text = _text_for_style(style)
                if _keyword_overlap(model_text, style_text) >= 2:
                    if not graph.has_edge(model_id, style_id):
                        graph.add_edge(model_id, style_id, edge_type="INFORMS")

    logger.info(
        "Edge building complete: %d total edges",
        graph.number_of_edges(),
    )
