"""Session state for batch post generation — persists across all 10 source runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tracer import BatchTracer
    from .inventory_state import PackInventoryState


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
    stories_used: list[str] = field(default_factory=list)
    argument_compressed: str = ""
    saturation_warning: dict = field(default_factory=dict)
    quality_flags: dict = field(default_factory=dict)
    regen_count: int = 0
    actual_mechanic: str = ""
    # v5 fields populated by 03_generate.txt
    closer_mechanic: str = ""        # one of 8 closer enum values
    authority_anchor: str = ""       # which verified founder anchor was used
    body_format: str = ""            # body format mold the post uses
    body_divergence_check: list[str] = field(default_factory=list)
    strip_test_residue: str = ""

    # v6 fields — 9.7+ floor system
    pre_commit: dict = field(default_factory=dict)        # the generator's declaration block
    self_scores: dict = field(default_factory=dict)       # generator's 10-parameter self-rating
    validator_scores: dict = field(default_factory=dict)  # validator's 10-parameter scoring
    passes_9_7_floor: bool = False                        # validator's binary verdict
    regen_history: list[dict] = field(default_factory=list)  # per-attempt failure context
    anchor_consumed_id: str = ""                          # which anchor_id this post consumed
    surprise_quotient: dict = field(default_factory=dict)  # description + type + traceability

    # v6.1 sub-mechanic tracking (populated by validator)
    actual_sub_mechanic_used: str = ""    # what sub-mechanic the post actually used
    required_sub_mechanic: str = ""       # what sub-mechanic the source required
    sub_mechanic_match: bool = False      # did they align?
    parameter_1_hard_veto_triggered: bool = False  # mirror discipline violation


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
    voice_load: dict = field(default_factory=dict)  # full v5 01_voice_load result
    voice_markers: list[str] = field(default_factory=list)
    founder_ctx: dict = field(default_factory=dict)
    raw_data: dict = field(default_factory=dict)
    personality_card: str = ""
    median_word_count: int = 230
    word_count_range: tuple[int, int] = (160, 300)
    formatting_habits: dict = field(default_factory=dict)
    calibration_paragraph: str = ""
    founder_first_name: str = ""    # derived from founder_slug, used by v5 third-person filter

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

    # v6 — anchor inventory (from 00_anchor_inventory.txt), voice marker budget
    # (from 01_voice_load.txt voice_markers_with_budget), pack_history (30-day
    # rolling), per-pack inventory state (set/reset per source), routing
    # decision (from 02_dissect.txt source_fitness_check), and regen log.
    anchor_inventory: dict = field(default_factory=dict)
    voice_marker_budget: list[dict] = field(default_factory=list)
    pack_history: list[dict] = field(default_factory=list)
    inventory: "PackInventoryState | None" = field(default=None, repr=False)
    routing_decision: str = "generate_4_batch_a_5_batch_b"
    # True when dissect's routing_decision was overridden to force 4A+5B
    # despite a sub-mechanic mismatch. Downstream regen loop should skip
    # the mirror-integrity early-reject branch when this is set — the
    # mismatch is known and accepted by the user.
    force_4a_5b_applied: bool = False
    regen_log: list[dict] = field(default_factory=list)

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
