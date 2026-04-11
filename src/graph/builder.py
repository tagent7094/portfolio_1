"""Build the knowledge graph from extracted data.

Fixes from original:
- Issue #1:  Validates IDs, replaces snake_case_identifier with slugified content
- Issue #2:  Calls deduplicate_graph() post-build when merging
- Issue #3:  Rejects multi-topic junk drawer beliefs (splits them)
- Issue #4:  USES_STYLE edges use semantic matching not cartesian product
- Issue #5:  Creates BEST_FOR edges from story.best_used_for
- Issue #6:  Rejects placeholder best_used_for values
- Issue #7:  Populates label field on all node types
- Issue #8:  Shared topic normalization with query module
- Issue #10: Contrast pairs get their own category hub
- Issue #11: Sanitizes personality card (strips prompt instructions)
- Issue #12: Populates engagement and times_used from extraction data
- Issue #14: Normalizes pipe-separated rule_types to primary type
- Issue #15: Validates pronoun_rules are substantive
- Issue #16: Validates opposes field isn't generic filler
- Issue #17: Properly splits compound contrast pairs on |
- Issue #18: Rejects N/A contrast pairs
- Issue #21: Validates emotional registers against enum
- Issue #23: Handles pipe-separated topic fields correctly
- Issue #24: Cross-validates phrases_used against known anti-patterns
- Issue #25: Minimum strength threshold on SUPPORTS edges
"""

from __future__ import annotations

import logging
import re
import sys
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
    VALID_REGISTERS,
    VALID_RULE_TYPES,
    VALID_VIRALITY,
)

logger = logging.getLogger(__name__)

# ── Stopwords ─────────────────────────────────────────────────────────────

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

# ── Shared topic normalization (used by both builder and query) ────────────

TOPIC_CANONICAL: dict[str, str] = {
    "ai": "ai_technology",
    "artificial intelligence": "ai_technology",
    "automation": "ai_technology",
    "machine learning": "ai_technology",
    "ml": "ai_technology",
    "tech": "ai_technology",
    "technology": "ai_technology",
    "ai_automation": "ai_technology",
    "ai_augmentation": "ai_technology",
    "ai augmentation": "ai_technology",
    "ai augmentation vs automation": "ai_technology",
    "hiring": "talent",
    "talent": "talent",
    "recruitment": "talent",
    "recruiting": "talent",
    "team": "talent",
    "culture": "talent",
    "hiring & talent": "talent",
    "fundraising": "fundraising",
    "funding": "fundraising",
    "vc": "fundraising",
    "investor": "fundraising",
    "investors": "fundraising",
    "venture capital": "fundraising",
    "investment": "fundraising",
    "capital": "fundraising",
    "series": "fundraising",
    "sales": "sales_growth",
    "enterprise": "sales_growth",
    "revenue": "sales_growth",
    "growth": "sales_growth",
    "scaling": "sales_growth",
    "scale": "sales_growth",
    "deals": "sales_growth",
    "closing": "sales_growth",
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
    "market timing": "industry",
    "product": "product",
    "innovation": "product",
    "building": "product",
    "engineering": "product",
    "product management": "product",
    "personal": "personal",
    "identity": "personal",
    "accent": "personal",
    "bias": "personal",
    "diversity": "personal",
    "inclusion": "personal",
    "empathy": "personal",
    "resilience": "personal",
    "human connection": "personal",
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

# Known placeholder / garbage values to reject
_PLACEHOLDER_IDS = frozenset({
    "snake_case_identifier", "unknown", "example", "placeholder",
    "topic1", "topic2", "topic3", "test",
})

_PLACEHOLDER_BEST_USED = frozenset({
    "topic1", "topic2", "topic3", "example1", "example2",
})

_GENERIC_OPPOSES = frozenset({
    "metrics over narrative",
    "metrics over narrative fit",
    "mainstream belief",
    "conventional wisdom",
    "",
})

_NA_VALUES = frozenset({"n/a", "na", "none", "null", "n/a (gratitude story)", "-"})

# Known anti-patterns that should never be in phrases_used
_ANTI_PATTERN_PHRASES = frozenset({
    "here's what people miss",
    "let me be honest",
    "unpopular opinion",
    "hot take",
    "controversial opinion",
    "let that sink in",
})


# ── Helpers ───────────────────────────────────────────────────────────────

def _tokenize(text: str) -> set[str]:
    """Tokenize text into lowercase keyword set, stripping stopwords."""
    words = re.findall(r"[a-z][a-z']+", text.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 2}


def _keyword_overlap(text_a: str, text_b: str) -> int:
    """Return count of shared meaningful keywords between two texts."""
    return len(_tokenize(text_a) & _tokenize(text_b))


def _slugify(text: str, max_len: int = 50) -> str:
    """Create a clean snake_case slug from text."""
    clean = re.sub(r"[^a-z0-9 ]", "", text.lower().strip())
    slug = "_".join(clean.split())
    return slug[:max_len] if slug else "unknown"


def _is_placeholder_id(raw_id: str) -> bool:
    """Check if an ID is a placeholder that needs replacement."""
    lower = raw_id.lower().strip()
    if any(p in lower for p in _PLACEHOLDER_IDS):
        return True
    # Pure numeric or very short
    if lower.isdigit() or len(lower) < 3:
        return True
    return False


def _generate_belief_id(belief: dict) -> str:
    """Generate a meaningful ID from belief content."""
    # Use topic + first few stance words
    topic = _slugify(belief.get("topic", ""), 20)
    stance = _slugify(belief.get("stance", ""), 30)
    if topic and stance:
        return f"{topic}_{stance}"
    return stance or topic or "unknown"


def _generate_story_id(story: dict) -> str:
    """Generate a meaningful ID from story content."""
    title = _slugify(story.get("title", ""), 50)
    return title or _slugify(story.get("summary", "")[:60], 50) or "unknown"


def _generate_style_id(rule: dict) -> str:
    """Generate a meaningful ID from style rule content."""
    desc = _slugify(rule.get("description", ""), 50)
    rtype = _slugify(rule.get("rule_type", ""), 15)
    if rtype and desc:
        return f"{rtype}_{desc}"
    return desc or rtype or "unknown"


def _generate_model_id(model: dict) -> str:
    """Generate a meaningful ID from thinking model content."""
    return _slugify(model.get("name", ""), 50) or _slugify(model.get("description", "")[:60], 50)


def normalize_topic(topic: str) -> set[str]:
    """Map a topic string to a set of canonical topic buckets.

    Handles pipe-separated, slash-separated, and compound topics.
    This is the SHARED normalization used by both builder and query.
    """
    # Split on pipes, slashes, commas, ampersands
    parts = re.split(r"[|/,&]+", topic.lower())
    buckets = set()

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Direct match
        if part in TOPIC_CANONICAL:
            buckets.add(TOPIC_CANONICAL[part])
            continue

        # Try each word
        words = re.split(r"[\s_]+", part)
        for word in words:
            word = word.strip()
            if word in TOPIC_CANONICAL:
                buckets.add(TOPIC_CANONICAL[word])

        # If no match found, use the cleaned part as-is
        if not any(w.strip() in TOPIC_CANONICAL for w in words):
            cleaned = _slugify(part, 30)
            if cleaned:
                buckets.add(cleaned)

    return buckets if buckets else {"general"}


def _normalize_register(raw: str) -> str:
    """Normalize an emotional register value to a valid single value.

    Handles misspellings, pipe-separated values, and invalid values.
    """
    if not raw:
        return "quiet_authority"

    raw_lower = raw.lower().strip()

    # Fix known misspellings
    if "generated" in raw_lower:
        raw_lower = raw_lower.replace("generated", "earned")

    # Split on pipes and take the first valid one
    parts = re.split(r"[|,]+", raw_lower)
    for part in parts:
        part = part.strip().replace(" ", "_")
        if part in VALID_REGISTERS:
            return part

    # Fuzzy match
    for valid in VALID_REGISTERS:
        if valid in raw_lower or raw_lower in valid:
            return valid

    return "quiet_authority"


def _normalize_rule_type(raw: str) -> str:
    """Normalize a rule_type to a single valid value.

    Handles pipe-separated, comma-separated, and compound values.
    """
    if not raw:
        return "rhetorical_move"

    raw_lower = raw.lower().strip()

    # Direct match
    if raw_lower in VALID_RULE_TYPES:
        return raw_lower

    # Split on pipes, commas, spaces-with-keywords
    parts = re.split(r"[|,]+", raw_lower)
    for part in parts:
        part = part.strip().replace(" ", "_")
        if part in VALID_RULE_TYPES:
            return part

    # Fuzzy: check if any valid type is a substring
    for valid in VALID_RULE_TYPES:
        if valid in raw_lower:
            return valid

    return "rhetorical_move"


def _sanitize_personality_card(card: str) -> str:
    """Remove prompt instructions leaked into the personality card."""
    if not card:
        return ""

    # Common prompt instruction patterns to strip
    patterns = [
        r"Write the personality card now\.?.*$",
        r"Return ONLY the card text.*$",
        r"no preamble,? no explanation,? no metadata\.?",
        r"^You are instructed to.*?\n",
    ]
    result = card
    for pattern in patterns:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE | re.DOTALL)

    return result.strip()


def _validate_opposes(opposes: str | None, stance: str) -> str | None:
    """Validate the opposes field isn't generic filler."""
    if not opposes:
        return None
    if opposes.lower().strip() in _GENERIC_OPPOSES:
        return None
    # If opposes is identical to stance, it's self-referential garbage
    if opposes.strip().lower() == stance.strip().lower():
        return None
    return opposes


def _validate_evidence_quotes(quotes: list[str], stance: str) -> list[str]:
    """Remove empty, duplicate, and stance-identical evidence quotes."""
    seen = set()
    valid = []
    stance_lower = stance.lower().strip()
    for q in quotes:
        if not q or not q.strip():
            continue
        q_clean = q.strip()
        q_lower = q_clean.lower()
        # Skip if it's just restating the stance
        if q_lower == stance_lower:
            continue
        # Skip duplicates
        if q_lower in seen:
            continue
        seen.add(q_lower)
        valid.append(q_clean)
    return valid


def _validate_phrases_used(phrases: list[str]) -> list[str]:
    """Remove known anti-patterns from phrases_used."""
    return [p for p in phrases if p.lower().strip() not in _ANTI_PATTERN_PHRASES]


def _validate_pronoun_rules(rules: dict) -> dict:
    """Check if pronoun rules are substantive or placeholder."""
    if not rules:
        return {}
    placeholder_hints = {"when and how they use", "when and how"}
    validated = {}
    for pronoun, rule in rules.items():
        if isinstance(rule, str) and any(h in rule.lower() for h in placeholder_hints):
            continue  # Skip placeholder descriptions
        validated[pronoun] = rule
    return validated


def _split_compound_contrast(cp_str: str) -> list[tuple[str, str, str]]:
    """Split a compound contrast pair string into individual (left, right, description) tuples.

    Handles formats like:
    - "X vs Y"
    - "X vs Y | A vs B"
    - "X vs Y | extra context"
    """
    if not cp_str or cp_str.lower().strip() in _NA_VALUES:
        return []

    # Split on | first to separate compound pairs
    segments = [s.strip() for s in cp_str.split("|") if s.strip()]

    pairs = []
    pending_context = []

    for seg in segments:
        # Check if this segment contains "vs"
        vs_match = re.split(r"\s+vs\.?\s+", seg, flags=re.IGNORECASE)
        if len(vs_match) >= 2:
            left = vs_match[0].strip()
            right = vs_match[1].strip()
            if left and right:
                desc = f"{left} vs {right}"
                pairs.append((left, right, desc))
        else:
            # Context fragment without vs — attach to previous pair or skip
            pending_context.append(seg)

    # If we got no pairs but have the original string with vs, do simple split
    if not pairs:
        vs_match = re.split(r"\s+vs\.?\s+", cp_str, flags=re.IGNORECASE)
        if len(vs_match) >= 2:
            left = vs_match[0].strip()
            right = vs_match[1].strip()
            # Clean right of any remaining | content
            right = right.split("|")[0].strip()
            if left and right:
                pairs.append((left, right, f"{left} vs {right}"))

    return pairs


def _ensure_list(val) -> list:
    """Coerce a value to a list of strings, filtering placeholders."""
    if val is None:
        return []
    if isinstance(val, str):
        if val.lower().strip() in _PLACEHOLDER_BEST_USED:
            return []
        return [val]
    if isinstance(val, list):
        return [str(x) for x in val if str(x).lower().strip() not in _PLACEHOLDER_BEST_USED]
    return [str(val)]


def _ensure_str(val) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    return str(val)


def _text_for_story(story_data: dict) -> str:
    parts = [
        _ensure_str(story_data.get("title", "")),
        _ensure_str(story_data.get("summary", "")),
        " ".join(_ensure_list(story_data.get("best_used_for"))),
        " ".join(_ensure_list(story_data.get("key_quotes"))),
    ]
    return " ".join(parts)


def _text_for_belief(belief_data: dict) -> str:
    parts = [
        _ensure_str(belief_data.get("topic", "")),
        _ensure_str(belief_data.get("stance", "")),
        _ensure_str(belief_data.get("opposes", "")),
    ]
    return " ".join(parts)


def _text_for_model(model_data: dict) -> str:
    return f"{_ensure_str(model_data.get('name', ''))} {_ensure_str(model_data.get('description', ''))}"


def _text_for_style(style_data: dict) -> str:
    parts = [
        _ensure_str(style_data.get("description", "")),
        " ".join(_ensure_list(style_data.get("examples"))),
        _ensure_str(style_data.get("anti_pattern", "")),
    ]
    return " ".join(parts)


# ── Belief splitting ──────────────────────────────────────────────────────

def _maybe_split_belief(belief: dict) -> list[dict]:
    """If a belief has multiple pipe-separated topics and >5 evidence quotes,
    it's a junk drawer. Split it into focused beliefs."""
    topic = belief.get("topic", "")
    evidence = belief.get("evidence_quotes", [])
    if not isinstance(evidence, list):
        evidence = [evidence] if evidence else []

    # Check for multi-topic junk drawer
    topic_parts = re.split(r"[|,]+", topic)
    if len(topic_parts) <= 2 or len(evidence) <= 5:
        return [belief]  # Not a junk drawer

    # Split: create one belief per major topic, distribute evidence
    results = []
    for part in topic_parts[:5]:  # Cap at 5 sub-beliefs
        part = part.strip()
        if not part or len(part) < 3:
            continue
        new_belief = {
            **belief,
            "topic": part,
            "id": _slugify(f"{part}_{belief.get('stance', '')[:30]}", 50),
            "evidence_quotes": [],  # Will be populated below
        }
        # Assign evidence that mentions this topic
        topic_words = _tokenize(part)
        for quote in evidence:
            quote_words = _tokenize(quote)
            if len(topic_words & quote_words) >= 1:
                new_belief["evidence_quotes"].append(quote)

        if new_belief["evidence_quotes"] or new_belief.get("stance"):
            results.append(new_belief)

    return results if results else [belief]


# ── Main builder ──────────────────────────────────────────────────────────

def build_graph(
    extracted_data: dict,
    existing_graph: nx.DiGraph | None = None,
    run_post_dedup: bool = True,
    embedder=None,
    save_path: str | None = None,
    on_node_added: callable | None = None,
) -> nx.DiGraph:
    """Build or merge a knowledge graph from extracted data.

    Args:
        extracted_data: dict with keys: beliefs, stories, style_rules,
                       thinking_models, vocabulary, personality_card
        existing_graph: optional existing graph to merge into
        run_post_dedup: if True, run post-build dedup
        embedder: optional embedder for deduplication
        save_path: if set, auto-save after every node (crash-safe live build)
        on_node_added: callback(graph, node_id, node_type, stats) for live UI
    """
    graph = existing_graph if existing_graph is not None else nx.DiGraph()
    stats = {"beliefs": 0, "stories": 0, "style_rules": 0, "models": 0,
             "contrast_pairs": 0, "skipped": 0, "total": 0, "phase": "init"}

    def _checkpoint(node_id: str | None = None, node_type: str = ""):
        """Save graph to disk after each node — crash-safe incremental build."""
        if save_path:
            from .store import save_graph as _save
            try:
                _save(graph, save_path)
            except Exception as e:
                _log(f"WARNING checkpoint save failed: {e}")
        if on_node_added and node_id:
            try:
                on_node_added(graph, node_id, node_type, {**stats})
            except Exception:
                pass

    # ── Founder node ──
    stats["phase"] = "founder"
    founder_label = "Founder"
    pc = extracted_data.get("personality_card", "")
    if pc:
        for line in pc.split("\n")[:5]:
            lower = line.lower()
            match = re.search(r"(?:you are|founder of|ceo of|co-founder)\s+(\w+)", lower)
            if match:
                founder_label = match.group(1).title()
                break

    if "founder" not in graph:
        graph.add_node("founder", node_type="founder", label=founder_label, description="Central founder node")

    # ── Category hubs ──
    stats["phase"] = "categories"
    for cat_id, cat_info in CATEGORY_HUBS.items():
        if cat_id not in graph:
            graph.add_node(cat_id, node_type="category", label=cat_info["label"],
                           category_type=cat_info["category_type"])
        if not graph.has_edge("founder", cat_id):
            graph.add_edge("founder", cat_id, edge_type="HAS_CATEGORY")

    _checkpoint("founder", "founder")

    # ── Beliefs ──
    stats["phase"] = "beliefs"
    _log(f"Adding beliefs ({len(extracted_data.get('beliefs', []))} raw)...")
    for belief in extracted_data.get("beliefs", []):
        sub_beliefs = _maybe_split_belief(belief)
        for sub in sub_beliefs:
            raw_id = sub.get("id", "unknown")
            if _is_placeholder_id(raw_id):
                raw_id = _generate_belief_id(sub)
            node_id = f"belief_{raw_id}"
            stance = _ensure_str(sub.get("stance", ""))
            if not stance:
                stats["skipped"] += 1
                continue

            if node_id in graph:
                existing = graph.nodes[node_id]
                old_quotes = existing.get("evidence_quotes", [])
                new_quotes = sub.get("evidence_quotes", [])
                if isinstance(new_quotes, str):
                    new_quotes = [new_quotes]
                merged = _validate_evidence_quotes(old_quotes + new_quotes, stance)
                existing["evidence_quotes"] = merged
            else:
                evidence = sub.get("evidence_quotes", [])
                if isinstance(evidence, str):
                    evidence = [evidence]
                elif sub.get("evidence_quote"):
                    evidence = [sub["evidence_quote"]]
                evidence = _validate_evidence_quotes(evidence, stance)
                opposes = _validate_opposes(sub.get("opposes"), stance)
                topics = normalize_topic(sub.get("topic", "general"))
                node = BeliefNode(
                    id=node_id, topic=sub.get("topic", "general"), stance=stance,
                    confidence=min(max(sub.get("confidence", 0.5), 0.0), 1.0),
                    evidence_quotes=evidence, opposes=opposes, label=stance[:80],
                )
                graph.add_node(node_id, **asdict(node), node_type="belief", topic_buckets=list(topics))
                stats["beliefs"] += 1
                stats["total"] += 1
                _checkpoint(node_id, "belief")

            if not graph.has_edge("cat_beliefs", node_id):
                graph.add_edge("cat_beliefs", node_id, edge_type="CONTAINS")
    _log(f"  -> {stats['beliefs']} beliefs added")

    # ── Stories ──
    stats["phase"] = "stories"
    _log(f"Adding stories ({len(extracted_data.get('stories', []))} raw)...")
    for story in extracted_data.get("stories", []):
        raw_id = story.get("id", "unknown")
        if _is_placeholder_id(raw_id):
            raw_id = _generate_story_id(story)
        node_id = f"story_{raw_id}"
        if node_id in graph:
            continue
        register = _normalize_register(story.get("emotional_register", ""))
        best_used_for = _ensure_list(story.get("best_used_for", []))
        virality = story.get("virality_potential", "medium")
        if virality not in VALID_VIRALITY:
            virality = "medium"
        node = StoryNode(
            id=node_id, title=_ensure_str(story.get("title", "")),
            summary=_ensure_str(story.get("summary", "")),
            emotional_register=register, contrast_pair=story.get("contrast_pair"),
            best_used_for=best_used_for,
            key_quotes=_ensure_list(story.get("key_quotes", [])),
            engagement=int(story.get("engagement", 0)),
            times_used=int(story.get("times_used", 0)),
            virality_potential=virality, label=_ensure_str(story.get("title", ""))[:80],
        )
        graph.add_node(node_id, **asdict(node), node_type="story")
        stats["stories"] += 1
        stats["total"] += 1
        if not graph.has_edge("cat_stories", node_id):
            graph.add_edge("cat_stories", node_id, edge_type="CONTAINS")
        _checkpoint(node_id, "story")
    _log(f"  -> {stats['stories']} stories added")

    # ── Style rules ──
    stats["phase"] = "style_rules"
    _log(f"Adding style rules ({len(extracted_data.get('style_rules', []))} raw)...")
    for rule in extracted_data.get("style_rules", []):
        raw_id = rule.get("id", "unknown")
        if _is_placeholder_id(raw_id):
            raw_id = _generate_style_id(rule)
        node_id = f"style_{raw_id}"
        if node_id in graph:
            continue
        description = _ensure_str(rule.get("description", ""))
        if not description:
            stats["skipped"] += 1
            continue
        rule_type = _normalize_rule_type(rule.get("rule_type", ""))
        node = StyleRuleNode(
            id=node_id, rule_type=rule_type, description=description,
            examples=_ensure_list(rule.get("examples", [])),
            anti_pattern=rule.get("anti_pattern"),
            platform=rule.get("platform", "universal"), label=description[:80],
        )
        graph.add_node(node_id, **asdict(node), node_type="style_rule")
        stats["style_rules"] += 1
        stats["total"] += 1
        if not graph.has_edge("cat_style", node_id):
            graph.add_edge("cat_style", node_id, edge_type="CONTAINS")
        _checkpoint(node_id, "style_rule")
    _log(f"  -> {stats['style_rules']} style rules added")

    # ── Thinking models ──
    stats["phase"] = "thinking_models"
    _log(f"Adding thinking models ({len(extracted_data.get('thinking_models', []))} raw)...")
    for model in extracted_data.get("thinking_models", []):
        raw_id = model.get("id", "unknown")
        if _is_placeholder_id(raw_id):
            raw_id = _generate_model_id(model)
        node_id = f"model_{raw_id}"
        if node_id in graph:
            continue
        name = _ensure_str(model.get("name", ""))
        description = _ensure_str(model.get("description", ""))
        node = ThinkingModelNode(
            id=node_id, name=name, description=description,
            priority=int(model.get("priority", 0)),
            label=name[:80] or description[:80],
        )
        graph.add_node(node_id, **asdict(node), node_type="thinking_model")
        stats["models"] += 1
        stats["total"] += 1
        if not graph.has_edge("cat_models", node_id):
            graph.add_edge("cat_models", node_id, edge_type="CONTAINS")
        _checkpoint(node_id, "thinking_model")
    _log(f"  -> {stats['models']} thinking models added")

    # ── Vocabulary ──
    stats["phase"] = "vocabulary"
    vocab = extracted_data.get("vocabulary", {})
    if vocab:
        phrases_used = _validate_phrases_used(vocab.get("phrases_used", []))
        pronoun_rules = _validate_pronoun_rules(vocab.get("pronoun_rules", {}))
        node = VocabularyNode(
            phrases_used=phrases_used,
            phrases_never=vocab.get("phrases_never", []),
            pronoun_rules=pronoun_rules,
        )
        graph.add_node("vocabulary", **asdict(node), node_type="vocabulary")
        if not graph.has_edge("cat_vocabulary", "vocabulary"):
            graph.add_edge("cat_vocabulary", "vocabulary", edge_type="CONTAINS")
        _checkpoint("vocabulary", "vocabulary")

    # ── Personality card ──
    if extracted_data.get("personality_card"):
        graph.graph["personality_card"] = _sanitize_personality_card(extracted_data["personality_card"])
        _checkpoint(None, "personality_card")

    # ── Build cross-type edges ──
    stats["phase"] = "edges"
    _log("Building edges...")
    _build_edges(graph)
    _checkpoint(None, "edges")
    _log(f"  -> {graph.number_of_edges()} edges total")

    # ── Post-build dedup ──
    stats["phase"] = "dedup"
    if run_post_dedup:
        _log("Running dedup...")
        from .dedup import deduplicate_graph
        graph, dedup_stats = deduplicate_graph(graph, embedder)
        logger.info("Post-build dedup: %s", dedup_stats)
        _checkpoint(None, "dedup")

    stats["phase"] = "done"
    _log(f"Graph built: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges | "
         f"{stats['beliefs']}B {stats['stories']}S {stats['style_rules']}R {stats['models']}M "
         f"({stats['skipped']} skipped)")

    # Final save
    if save_path:
        from .store import save_graph as _save
        _save(graph, save_path)
        _log(f"Final save -> {save_path}")

    return graph


# ── Edge building ─────────────────────────────────────────────────────────

_MIN_SUPPORT_STRENGTH = 2  # Issue #25: minimum keyword overlap for SUPPORTS edges
_MIN_STYLE_OVERLAP = 4     # Issue #4, #19: raised from 3 to reduce noise
_MIN_INFORMS_OVERLAP = 3   # Raised from 2


def _build_edges(graph: nx.DiGraph):
    """Create cross-type edges with tighter semantic matching."""
    beliefs = [(n, graph.nodes[n]) for n in graph if graph.nodes[n].get("node_type") == "belief"]
    stories = [(n, graph.nodes[n]) for n in graph if graph.nodes[n].get("node_type") == "story"]
    models = [(n, graph.nodes[n]) for n in graph if graph.nodes[n].get("node_type") == "thinking_model"]
    styles = [(n, graph.nodes[n]) for n in graph if graph.nodes[n].get("node_type") == "style_rule"]
    has_vocab = "vocabulary" in graph

    # ── A. Story → Belief (SUPPORTS) ──
    for story_id, story in stories:
        story_text = _text_for_story(story)
        story_tokens = _tokenize(story_text)
        story_topics = set()
        for bf in story.get("best_used_for", []):
            story_topics.update(normalize_topic(bf))

        for belief_id, belief in beliefs:
            belief_topics = set(belief.get("topic_buckets", []))
            if not belief_topics:
                belief_topics = normalize_topic(belief.get("topic", ""))

            belief_text = _text_for_belief(belief)
            belief_tokens = _tokenize(belief_text)

            # Strategy 1: topic bucket overlap
            topic_match = bool(story_topics & belief_topics)

            # Strategy 2: keyword overlap
            overlap = len(story_tokens & belief_tokens)
            keyword_match = overlap >= 3

            # Must have BOTH topic match and some keyword support,
            # OR strong keyword overlap alone
            if (topic_match and overlap >= _MIN_SUPPORT_STRENGTH) or overlap >= 4:
                if not graph.has_edge(story_id, belief_id):
                    graph.add_edge(story_id, belief_id, edge_type="SUPPORTS", strength=overlap)

    # ── A2. Story → Topic (BEST_FOR) ── Issue #5, #20
    for story_id, story in stories:
        for topic_str in story.get("best_used_for", []):
            buckets = normalize_topic(topic_str)
            for bucket in buckets:
                # Find beliefs in this bucket
                for belief_id, belief in beliefs:
                    belief_topics = set(belief.get("topic_buckets", []))
                    if bucket in belief_topics:
                        if not graph.has_edge(story_id, belief_id):
                            graph.add_edge(story_id, belief_id, edge_type="BEST_FOR")
                        break  # One BEST_FOR per bucket per story

    # ── B. Belief → Belief (RELATED / CONTRADICTS) ──
    topic_groups: dict[str, list[str]] = defaultdict(list)
    for belief_id, belief in beliefs:
        for bucket in belief.get("topic_buckets", normalize_topic(belief.get("topic", ""))):
            topic_groups[bucket].append(belief_id)

    for topic, group in topic_groups.items():
        unique = list(set(group))
        if len(unique) > 1:
            for i, b1 in enumerate(unique):
                for b2 in unique[i + 1:]:
                    if not graph.has_edge(b1, b2) and not graph.has_edge(b2, b1):
                        graph.add_edge(b1, b2, edge_type="RELATED")

    # CONTRADICTS: only when opposes is validated (not generic)
    for belief_id, belief in beliefs:
        opposes = belief.get("opposes") or ""
        if not opposes or len(opposes) < 15:
            continue
        opposes_tokens = _tokenize(opposes)
        if len(opposes_tokens) < 3:
            continue

        for other_id, other in beliefs:
            if other_id == belief_id:
                continue
            other_stance = other.get("stance", "")
            other_tokens = _tokenize(other_stance)
            overlap = len(opposes_tokens & other_tokens)
            # Need significant overlap AND the overlap tokens must be >30% of opposes tokens
            if overlap >= 4 and overlap / max(len(opposes_tokens), 1) > 0.3:
                if not graph.has_edge(belief_id, other_id):
                    graph.add_edge(belief_id, other_id, edge_type="CONTRADICTS")

    # ── C. Story → Style Rule (USES_STYLE) ── Issue #4, #19
    # CHANGED: Only use keyword overlap (not register affinity) to avoid cartesian explosion
    for story_id, story in stories:
        story_text = _text_for_story(story)
        story_tokens = _tokenize(story_text)

        matched_styles = 0
        for style_id, style in styles:
            style_text = _text_for_style(style)
            style_tokens = _tokenize(style_text)
            overlap = len(story_tokens & style_tokens)

            if overlap >= _MIN_STYLE_OVERLAP:
                if not graph.has_edge(story_id, style_id):
                    graph.add_edge(story_id, style_id, edge_type="USES_STYLE", strength=overlap)
                    matched_styles += 1

                # Cap at 8 style edges per story to prevent fan-out
                if matched_styles >= 8:
                    break

    # ── D. Thinking Model → Belief (INFORMS) ──
    for model_id, model in models:
        model_text = _text_for_model(model)
        model_tokens = _tokenize(model_text)

        matched = 0
        for belief_id, belief in beliefs:
            belief_text = _text_for_belief(belief)
            belief_tokens = _tokenize(belief_text)
            overlap = len(model_tokens & belief_tokens)
            if overlap >= _MIN_INFORMS_OVERLAP:
                if not graph.has_edge(model_id, belief_id):
                    graph.add_edge(model_id, belief_id, edge_type="INFORMS", strength=overlap)
                    matched += 1
                if matched >= 6:
                    break

    # ── E. Story → Thinking Model (DEMONSTRATES) ──
    for story_id, story in stories:
        story_text = _text_for_story(story)
        story_tokens = _tokenize(story_text)

        for model_id, model in models:
            model_name = model.get("name", "").lower()
            model_tokens = _tokenize(_text_for_model(model))

            name_match = model_name and len(model_name) > 5 and model_name in story_text.lower()
            overlap = len(story_tokens & model_tokens)
            keyword_match = overlap >= 4  # Raised from 3

            if name_match or keyword_match:
                if not graph.has_edge(story_id, model_id):
                    graph.add_edge(story_id, model_id, edge_type="DEMONSTRATES")

    # ── F. Vocabulary → Style Rules (CONSTRAINS) ──
    if has_vocab:
        for style_id, style in styles:
            if style.get("rule_type") == "vocabulary":
                if not graph.has_edge("vocabulary", style_id):
                    graph.add_edge("vocabulary", style_id, edge_type="CONSTRAINS")

    # ── G. Contrast Pairs ── Issue #10, #17, #18
    seen_pairs: dict[str, str] = {}
    for story_id, story in stories:
        cp_raw = story.get("contrast_pair")
        if not cp_raw:
            continue

        pairs = _split_compound_contrast(cp_raw)
        for left, right, desc in pairs:
            cp_key = f"{left.lower().strip()} vs {right.lower().strip()}"

            if cp_key in seen_pairs:
                cp_node_id = seen_pairs[cp_key]
            else:
                cp_slug = _slugify(f"{left} vs {right}", 60)
                cp_node_id = f"contrast_{cp_slug}"

                if cp_node_id not in graph:
                    graph.add_node(
                        cp_node_id,
                        node_type="contrast_pair",
                        left=left,
                        right=right,
                        description=desc,
                        label=desc[:60],
                    )
                    # Issue #10: use contrast category, not stories
                    if not graph.has_edge("cat_contrasts", cp_node_id):
                        graph.add_edge("cat_contrasts", cp_node_id, edge_type="CONTAINS")

                seen_pairs[cp_key] = cp_node_id

            if not graph.has_edge(story_id, cp_node_id):
                graph.add_edge(story_id, cp_node_id, edge_type="ILLUMINATES")

    # ── H. Thinking Model → Style Rule ──
    for model_id, model in models:
        model_text = _text_for_model(model)
        for style_id, style in styles:
            if style.get("rule_type") in ("rhetorical_move", "rhythm"):
                style_text = _text_for_style(style)
                if _keyword_overlap(model_text, style_text) >= 3:
                    if not graph.has_edge(model_id, style_id):
                        graph.add_edge(model_id, style_id, edge_type="INFORMS")


def _log(msg: str):
    print(f"\033[33m[GraphBuilder]\033[0m {msg}", file=sys.stderr, flush=True)
    logger.info(msg)