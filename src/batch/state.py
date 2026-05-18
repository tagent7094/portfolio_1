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
    weakness: str = ""
    versions_considered: int = 0
    opener_variants: list[dict] = field(default_factory=list)
    recommended_variant: str = ""
    voice_score: int = 0
    validation_result: dict = field(default_factory=dict)
    violations: list[str] = field(default_factory=list)
    events_used: list[str] = field(default_factory=list)
    argument_compressed: str = ""
    saturation_warning: dict = field(default_factory=dict)
    quality_flags: dict = field(default_factory=dict)
    regen_count: int = 0
    actual_mechanic: str = ""


@dataclass
class PackResult:
    source_number: int
    source_post: str
    dissection: dict = field(default_factory=dict)
    mirrorable: bool = True
    posts: list[AmplifiedPost] = field(default_factory=list)
    batch_a_count: int = 0
    batch_b_count: int = 0
    convergence_test_a: dict = field(default_factory=dict)
    convergence_test: dict = field(default_factory=dict)
    convergence_warning: bool = False
    convergence_retry_attempted: bool = False
    total_regens: int = 0


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
    calibration_paragraph: str = ""

    # Exclusions
    exclusions: list[str] = field(default_factory=list)

    # Freshness tracking
    freshness_warning: str = ""

    # Global freshness tracking
    events_used_global: set[str] = field(default_factory=set)
    stories_used_global: set[str] = field(default_factory=set)
    entry_doors_used: dict = field(default_factory=dict)
    arguments_compressed: list[str] = field(default_factory=list)

    # Per-source results
    source_posts: list[str] = field(default_factory=list)
    source_dissections: list[dict] = field(default_factory=list)
    packs: list[PackResult] = field(default_factory=list)

    # Marker rates (per-post averages from founder's published corpus)
    marker_rates: dict = field(default_factory=dict)

    # Story usage counter (story_name -> times used in this batch run)
    story_usage_counter: dict = field(default_factory=dict)

    # Amplifier log
    amplifier_log: list[dict] = field(default_factory=list)

    # Web search enrichment
    web_search_context: dict = field(default_factory=dict)

    # Tracer (set by session, not serialized)
    tracer: BatchTracer | None = field(default=None, repr=False)

    # Per-task LLM router (set by session, not serialized). When present, every
    # downstream LLM call should consult `state.llm_router.for_task(<task_id>)`
    # to honour admin defaults + founder overrides instead of using the bare
    # `llm` parameter it was passed.
    llm_router: object | None = field(default=None, repr=False)

    # Lean mode: batch multiple operations per LLM call to reduce total calls
    lean_mode: bool = False

    # Cost telemetry (USD). Populated by tracer after each LLM call.
    total_cost_usd: float = 0.0
    cost_by_task: dict = field(default_factory=dict)   # {"transpose": 1.42, "amplify": 0.31, ...}
    cost_by_model: dict = field(default_factory=dict)  # {"claude-opus-4-6": 1.50, "claude-haiku-4-5-20251001": 0.23}
    cost_by_pack: dict = field(default_factory=dict)   # {1: 2.31, 2: 2.15, 3: 1.98}
    total_input_tokens: int = 0
    total_output_tokens: int = 0
