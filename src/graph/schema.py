"""Node and edge type definitions for the knowledge graph.

Changes from original:
- Added `label` field to StyleRuleNode and ThinkingModelNode (Issue #7)
- Added VALID_REGISTERS and VALID_RULE_TYPES enums for validation (Issue #14, #21)
- Added contrast_pair category hub (Issue #10)
- Added engagement/times_used population path for StoryNode (Issue #12)
- Tightened defaults and docstrings
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ── Validation enums ──────────────────────────────────────────────────────

VALID_REGISTERS = frozenset({
    "controlled_anger",
    "quiet_authority",
    "earned_vulnerability",
    "generosity",
    "paranoid_optimist",
})

VALID_RULE_TYPES = frozenset({
    "opening",
    "closing",
    "rhythm",
    "rhetorical_move",
    "vocabulary",
    "punctuation",
    "formatting",
    "tone",
    "pronoun",
    "argument",
    "structural",
})

VALID_VIRALITY = frozenset({"high", "medium", "low"})


# ── Node dataclasses ──────────────────────────────────────────────────────

@dataclass
class BeliefNode:
    id: str
    topic: str
    stance: str
    confidence: float
    evidence_quotes: list[str] = field(default_factory=list)
    opposes: str | None = None
    source_chunks: list[str] = field(default_factory=list)
    label: str = ""


@dataclass
class StoryNode:
    id: str
    title: str
    summary: str
    emotional_register: str  # must be one of VALID_REGISTERS
    contrast_pair: str | None = None
    best_used_for: list[str] = field(default_factory=list)
    key_quotes: list[str] = field(default_factory=list)
    engagement: int = 0
    times_used: int = 0
    virality_potential: str = "medium"
    label: str = ""


@dataclass
class StyleRuleNode:
    id: str
    rule_type: str  # must be one of VALID_RULE_TYPES
    description: str
    examples: list[str] = field(default_factory=list)
    anti_pattern: str | None = None
    platform: str = "universal"
    label: str = ""  # Issue #7: was missing


@dataclass
class ThinkingModelNode:
    id: str
    name: str
    description: str
    priority: int = 0
    label: str = ""  # Issue #7: was missing


@dataclass
class ContrastPairNode:
    id: str
    left: str
    right: str
    description: str
    label: str = ""


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
    category_type: str = ""


# ── Edge types ────────────────────────────────────────────────────────────

EDGE_TYPES = {
    "SUPPORTS": "story -> belief (story provides evidence for a belief)",
    "CONTRADICTS": "belief -> counter_belief",
    "DEMONSTRATES": "story -> thinking_model",
    "ILLUMINATES": "story -> contrast_pair",
    "TRIGGERS": "register -> rhetorical_move",
    "BEST_FOR": "story -> topic (story is strong evidence for this topic)",
    "INFORMS": "thinking_model -> belief",
    "CONSTRAINS": "vocabulary -> style_rule",
    "HAS_CATEGORY": "founder -> category hub",
    "CONTAINS": "category hub -> individual node",
    "RELATED": "belief -> belief (same topic cluster)",
    "USES_STYLE": "story -> style_rule (meaningful stylistic connection)",
}

# ── Category hub definitions ──────────────────────────────────────────────

CATEGORY_HUBS = {
    "cat_beliefs": {"label": "Beliefs", "category_type": "beliefs"},
    "cat_stories": {"label": "Stories", "category_type": "stories"},
    "cat_style": {"label": "Style Rules", "category_type": "style_rules"},
    "cat_models": {"label": "Thinking Models", "category_type": "thinking_models"},
    "cat_vocabulary": {"label": "Vocabulary", "category_type": "vocabulary"},
    "cat_contrasts": {"label": "Contrast Pairs", "category_type": "contrast_pairs"},  # Issue #10
}