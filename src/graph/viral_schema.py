"""Schema for the Viral Posts Knowledge Graph (Big Brain)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class HookTypeNode:
    id: str
    hook_name: str
    template: str
    avg_engagement: float = 0
    example_hooks: list[str] = field(default_factory=list)
    count: int = 0
    why_it_works: str = ""


@dataclass
class StructureTemplateNode:
    id: str
    template_name: str
    structure_description: str
    paragraph_count_range: str = ""
    avg_word_count: int = 0
    avg_engagement: float = 0
    example_post_ids: list[str] = field(default_factory=list)


@dataclass
class TopicClusterNode:
    id: str
    cluster_name: str
    keywords: list[str] = field(default_factory=list)
    post_count: int = 0
    avg_engagement: float = 0
    top_performing_angle: str = ""
    engagement_range: str = ""


@dataclass
class ViralPatternNode:
    id: str
    pattern_name: str
    description: str
    frequency: int = 0
    avg_engagement: float = 0
    effectiveness_score: float = 0
    bracket: str = ""


@dataclass
class EngagementProfileNode:
    id: str
    bracket: str
    likes_range: str = ""
    comments_range: str = ""
    reposts_range: str = ""
    common_patterns: list[str] = field(default_factory=list)
    post_count: int = 0


@dataclass
class WritingTechniqueNode:
    id: str
    technique_name: str
    description: str
    impact_on_engagement: str = ""
    impact: str = "medium"
    frequency: int = 0
    example_snippets: list[str] = field(default_factory=list)
    example_snippet: str = ""


VIRAL_NODE_TYPES = [
    "hook_type", "structure_template", "topic_cluster",
    "viral_pattern", "engagement_profile", "writing_technique",
]

VIRAL_EDGE_TYPES = {
    "USES_HOOK": "structure_template -> hook_type",
    "FOLLOWS_STRUCTURE": "topic_cluster -> structure_template",
    "BELONGS_TO_CLUSTER": "hook_type -> topic_cluster",
    "EXHIBITS_PATTERN": "structure_template -> viral_pattern",
    "CORRELATES_WITH": "viral_pattern -> engagement_profile",
    "HOOK_FOR_CLUSTER": "hook_type -> topic_cluster",
    "TECHNIQUE_IN_PATTERN": "writing_technique -> viral_pattern",
}