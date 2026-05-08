"""Session state for batch post generation — persists across all 10 source runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tracer import BatchTracer


@dataclass
class AmplifiedPost:
    label: str                       # A1, A2, A3, B1..B6
    batch: str                       # "A" or "B"
    entry_door: str                  # "mirrored" for A, specific door for B
    mode: str                        # "wrestling" or "declaring"
    text: str                        # final post text
    word_count: int = 0
    original_opening: str = ""
    final_opening: str = ""
    mechanic: str = ""               # opener mechanic used
    gates: dict = field(default_factory=dict)
    rating: int = 0
    buried_gold: str = ""
    versions_considered: int = 0
    events_used: list[str] = field(default_factory=list)
    argument_compressed: str = ""


@dataclass
class PackResult:
    source_number: int
    source_post: str
    dissection: dict = field(default_factory=dict)
    mirrorable: bool = True
    posts: list[AmplifiedPost] = field(default_factory=list)
    batch_a_count: int = 0
    batch_b_count: int = 0
    convergence_test: dict = field(default_factory=dict)


@dataclass
class BatchState:
    founder_slug: str
    platform: str = "linkedin"
    creativity: float = 0.5

    # Phase 1 outputs
    founder_internalization: dict = field(default_factory=dict)
    voice_markers: list[str] = field(default_factory=list)
    founder_ctx: dict = field(default_factory=dict)
    raw_data: dict = field(default_factory=dict)
    personality_card: str = ""
    median_word_count: int = 230
    word_count_range: tuple[int, int] = (160, 300)
    formatting_habits: dict = field(default_factory=dict)

    # Global freshness tracking
    events_used_global: set[str] = field(default_factory=set)
    stories_used_global: set[str] = field(default_factory=set)
    entry_doors_used: dict = field(default_factory=dict)
    arguments_compressed: list[str] = field(default_factory=list)

    # Per-source results
    source_posts: list[str] = field(default_factory=list)
    source_dissections: list[dict] = field(default_factory=list)
    packs: list[PackResult] = field(default_factory=list)

    # Amplifier log
    amplifier_log: list[dict] = field(default_factory=list)

    # Web search enrichment
    web_search_context: dict = field(default_factory=dict)

    # Tracer (set by session, not serialized)
    tracer: BatchTracer | None = field(default=None, repr=False)
