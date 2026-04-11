"""Knowledge graph module for founder voice modeling."""

from .schema import (
    BeliefNode, StoryNode, StyleRuleNode, ThinkingModelNode,
    ContrastPairNode, VocabularyNode, FounderNode, CategoryNode,
    CATEGORY_HUBS, EDGE_TYPES, VALID_REGISTERS, VALID_RULE_TYPES,
)
from .builder import build_graph, normalize_topic
from .dedup import dedup_extracted_data, deduplicate_graph
from .query import (
    get_beliefs_for_topic, get_stories_for_beliefs, get_stories_for_topic,
    get_style_rules_for_platform, get_contrast_pairs, get_thinking_models,
    get_vocabulary_rules, get_personality_card, get_full_context,
    get_merged_context,
)
from .store import save_graph, load_graph

__all__ = [
    "build_graph", "normalize_topic",
    "dedup_extracted_data", "deduplicate_graph",
    "get_beliefs_for_topic", "get_stories_for_beliefs", "get_stories_for_topic",
    "get_style_rules_for_platform", "get_contrast_pairs", "get_thinking_models",
    "get_vocabulary_rules", "get_personality_card", "get_full_context",
    "get_merged_context",
    "save_graph", "load_graph",
    "BeliefNode", "StoryNode", "StyleRuleNode", "ThinkingModelNode",
    "ContrastPairNode", "VocabularyNode", "FounderNode", "CategoryNode",
    "CATEGORY_HUBS", "EDGE_TYPES", "VALID_REGISTERS", "VALID_RULE_TYPES",
]