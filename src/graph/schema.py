"""Node and edge type definitions for the knowledge graph."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BeliefNode:
    id: str
    topic: str
    stance: str
    confidence: float
    evidence_quotes: list[str] = field(default_factory=list)
    opposes: str | None = None
    source_chunks: list[str] = field(default_factory=list)


@dataclass
class StoryNode:
    id: str
    title: str
    summary: str
    emotional_register: str  # controlled_anger | quiet_authority | earned_vulnerability | generosity | paranoid_optimist
    contrast_pair: str | None = None
    best_used_for: list[str] = field(default_factory=list)
    key_quotes: list[str] = field(default_factory=list)
    engagement: int = 0
    times_used: int = 0
    virality_potential: str = "medium"


@dataclass
class StyleRuleNode:
    id: str
    rule_type: str  # opening | closing | rhythm | rhetorical_move | vocabulary | punctuation
    description: str
    examples: list[str] = field(default_factory=list)
    anti_pattern: str | None = None
    platform: str = "universal"


@dataclass
class ThinkingModelNode:
    id: str
    name: str
    description: str
    priority: int = 0


@dataclass
class ContrastPairNode:
    id: str
    left: str
    right: str
    description: str


@dataclass
class VocabularyNode:
    id: str = "vocabulary"
    phrases_used: list[str] = field(default_factory=list)
    phrases_never: list[str] = field(default_factory=list)
    pronoun_rules: dict = field(default_factory=dict)


@dataclass
class FounderNode:
    id: str = "founder"
    label: str = "Founder"
    description: str = ""


@dataclass
class CategoryNode:
    id: str = ""
    label: str = ""
    category_type: str = ""  # beliefs | stories | style_rules | thinking_models | vocabulary


# Edge types
EDGE_TYPES = {
    "SUPPORTS": "story -> belief (story provides evidence for a belief)",
    "CONTRADICTS": "belief -> counter_belief",
    "DEMONSTRATES": "story -> thinking_model",
    "ILLUMINATES": "story -> contrast_pair",
    "TRIGGERS": "register -> rhetorical_move",
    "BEST_FOR": "story -> topic",
    "INFORMS": "thinking_model -> belief",
    "CONSTRAINS": "vocabulary -> style_rule",
    "HAS_CATEGORY": "founder -> category hub",
    "CONTAINS": "category hub -> individual node",
    "RELATED": "belief -> belief (same topic cluster)",
    "USES_STYLE": "story -> style_rule",
}

# Category hub definitions
CATEGORY_HUBS = {
    "cat_beliefs": {"label": "Beliefs", "category_type": "beliefs"},
    "cat_stories": {"label": "Stories", "category_type": "stories"},
    "cat_style": {"label": "Style Rules", "category_type": "style_rules"},
    "cat_models": {"label": "Thinking Models", "category_type": "thinking_models"},
    "cat_vocabulary": {"label": "Vocabulary", "category_type": "vocabulary"},
}
