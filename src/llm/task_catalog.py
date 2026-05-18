"""Catalog of every distinct LLM-using task in the batch generation pipeline.

This is the source of truth that drives:
  - the per-task config UI (admin + founder)
  - the LLMRouter's hardcoded fallback when no admin config exists
  - the tracer's resolved-model logging

Each task entry records the original `purpose` bucket so deployments that
haven't authored a `models-config.json` keep working — the router maps the
purpose back to the legacy `llm` / `llm_prep` / `llm_ingestion` YAML section.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


Purpose = Literal["generation", "prep", "ingestion"]
Tier = Literal["heavy", "medium", "light"]
Frequency = Literal["per_batch", "per_source", "per_post", "per_pack", "conditional"]


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    display_name: str
    description: str
    call_site: str
    default_purpose: Purpose
    quality_tier: Tier
    frequency: Frequency
    streaming: bool = True
    web_search: bool = False
    default_temperature: float = 0.3
    default_max_tokens: int = 4000
    default_thinking_budget: int = 0


_RAW_TASKS: list[TaskSpec] = [
    # ── v6 tasks (7-prompt 9.7+ floor pipeline) ──
    TaskSpec(
        task_id="anchor_inventory",
        display_name="Anchor inventory (v6)",
        description="v6 00_anchor_inventory.txt — pre-flight constraint catalog. Runs ONCE per founder per run (cached). Lists verified anchors with mechanic-fit tags, voice marker budget, founder card depth.",
        call_site="src/batch/anchor_inventory.py:build_anchor_inventory",
        default_purpose="prep",
        quality_tier="medium",
        frequency="per_batch",
        default_temperature=0.2,
        default_max_tokens=8000,
        default_thinking_budget=0,
    ),
    TaskSpec(
        task_id="compile",
        display_name="Pack compile + accept/reject (v6)",
        description="v6 06_compile.txt — final binary ship/reject gate. Verifies every post meets 9.7+ floor on every parameter before Excel write. Surfaces rejection with recommendations when floor not met.",
        call_site="src/batch/compile_step.py:compile_pack",
        default_purpose="prep",
        quality_tier="medium",
        frequency="per_pack",
        default_temperature=0.2,
        default_max_tokens=4000,
        default_thinking_budget=0,
    ),
    # ── v5 tasks (5-prompt pipeline) ──
    TaskSpec(
        task_id="voice_load",
        display_name="Voice load (corpus + calibration)",
        description="v5 01_voice_load.txt — merges deep corpus internalization + calibration check + third-person filter into one call per pack.",
        call_site="src/batch/corpus_reader.py:voice_load",
        default_purpose="generation",
        quality_tier="heavy",
        frequency="per_batch",
        default_temperature=0.3,
        default_max_tokens=8000,
        default_thinking_budget=0,
    ),
    TaskSpec(
        task_id="generate",
        display_name="Generate post (sequential, v5)",
        description="v5 03_generate.txt — generates ONE post per call, sees prior_posts + anchors_remaining. Called 9× per pack (A1→A4→B1→B5) so later posts can diverge from earlier ones.",
        call_site="src/batch/pack_generator.py:_generate_one_post",
        default_purpose="generation",
        quality_tier="heavy",
        frequency="per_post",
        default_temperature=0.5,
        default_max_tokens=4000,
        default_thinking_budget=0,
    ),
    TaskSpec(
        task_id="validate",
        display_name="Validate pack (per-post + convergence)",
        description="v5 05_validate.txt — runs ONCE per pack. Per-post 5-dimension scoring + pack convergence check + cross-variant body diff.",
        call_site="src/batch/voice_validator.py:validate_pack",
        default_purpose="prep",
        quality_tier="medium",
        frequency="per_pack",
        default_temperature=0.2,
        default_max_tokens=3000,
        default_thinking_budget=0,
    ),
    # ── v4 legacy tasks (kept for back-compat with old configs) ──
    TaskSpec(
        task_id="internalize",
        display_name="Founder voice internalization (v4)",
        description="DEPRECATED v4 task — use `voice_load` for v5. Deep corpus reading — extracts voice markers, scenes, tensions, formatting habits.",
        call_site="src/batch/corpus_reader.py:internalize_corpus",
        default_purpose="generation",
        quality_tier="heavy",
        frequency="per_batch",
        default_temperature=0.3,
        default_max_tokens=6000,
        default_thinking_budget=10000,
    ),
    TaskSpec(
        task_id="calibration",
        display_name="Voice calibration check",
        description="Writes one test paragraph to verify voice calibration before generation begins.",
        call_site="src/batch/corpus_reader.py:calibration_check",
        default_purpose="generation",
        quality_tier="heavy",
        frequency="per_batch",
        default_temperature=0.5,
        default_max_tokens=1500,
    ),
    TaskSpec(
        task_id="web_search",
        display_name="Web search enrichment",
        description="Searches the web for trending topics and current facts about the founder and their domain.",
        call_site="src/batch/session.py:_web_search_enrich",
        default_purpose="prep",
        quality_tier="medium",
        frequency="per_batch",
        web_search=True,
        default_temperature=0.3,
        default_max_tokens=2000,
    ),
    TaskSpec(
        task_id="select_sources",
        display_name="Viral source ranking",
        description="Picks the top-N viral source posts for this batch from the founder's available pool.",
        call_site="src/batch/source_selector.py:select_sources",
        default_purpose="prep",
        quality_tier="medium",
        frequency="per_batch",
        default_temperature=0.3,
        default_max_tokens=2000,
    ),
    TaskSpec(
        task_id="dissect",
        display_name="Source hook dissection",
        description="Analyzes each source post's mechanic, body format, closer mechanic — the structural mold for Batch A mirroring.",
        call_site="src/batch/pack_generator.py:dissect_source",
        default_purpose="prep",
        quality_tier="medium",
        frequency="per_source",
        default_temperature=0.2,
        default_max_tokens=3000,
    ),
    TaskSpec(
        task_id="generate_a",
        display_name="Batch A — mirrored post",
        description="Generates 3 posts per source that mirror the source's opener mechanic, body format, and closer.",
        call_site="src/batch/pack_generator.py:_generate_a_variant",
        default_purpose="generation",
        quality_tier="heavy",
        frequency="per_source",
        default_temperature=0.5,
        default_max_tokens=1500,
        default_thinking_budget=12000,
    ),
    TaskSpec(
        task_id="generate_b",
        display_name="Batch B — mechanics-only post",
        description="Generates 6 posts per source using assigned entry doors (scene_drop, contrarian, parallel, etc).",
        call_site="src/batch/pack_generator.py:_generate_b_variant",
        default_purpose="generation",
        quality_tier="heavy",
        frequency="per_source",
        default_temperature=0.5,
        default_max_tokens=1500,
        default_thinking_budget=12000,
    ),
    TaskSpec(
        task_id="word_count_trim",
        display_name="Post length trim (LLM)",
        description="Trims a post that exceeds the founder's word-count band — conditional, fires only when mechanical trim couldn't.",
        call_site="src/batch/pack_generator.py:_llm_trim_post",
        default_purpose="generation",
        quality_tier="light",
        frequency="conditional",
        default_temperature=0.2,
        default_max_tokens=800,
    ),
    TaskSpec(
        task_id="voice_validation",
        display_name="Voice quality check",
        description="Scores each generated post for voice marker presence and register fit. Runs on every post.",
        call_site="src/batch/voice_validator.py:validate_voice",
        default_purpose="generation",
        quality_tier="medium",
        frequency="per_post",
        default_temperature=0.3,
        default_max_tokens=3000,
        default_thinking_budget=10000,
    ),
    TaskSpec(
        task_id="voice_regen",
        display_name="Voice override regeneration",
        description="Regenerates a post when voice validation fails. Conditional, fires only on FAIL.",
        call_site="src/batch/voice_validator.py:regenerate_with_voice_override",
        default_purpose="generation",
        quality_tier="heavy",
        frequency="conditional",
        default_temperature=0.5,
        default_max_tokens=2000,
        default_thinking_budget=12000,
    ),
    TaskSpec(
        task_id="amplify",
        display_name="Amplifier — 7-gate diagnosis + 5 variants",
        description="Combined opener amplifier: diagnoses through 7 gates and generates 5 alternative openings in one call.",
        call_site="src/batch/amplifier.py:amplify_post_v2",
        default_purpose="generation",
        quality_tier="medium",
        frequency="per_post",
        default_temperature=0.3,
        default_max_tokens=6000,
        default_thinking_budget=0,
    ),
    TaskSpec(
        task_id="convergence_test",
        display_name="Pack divergence check",
        description="Tests whether the pack's posts argue too-similar things. Returns replacement angles when FAIL.",
        call_site="src/batch/amplifier.py:convergence_test",
        default_purpose="prep",
        quality_tier="medium",
        frequency="per_pack",
        default_temperature=0.2,
        default_max_tokens=2000,
    ),
    # ── Lean-mode generation (transpose produces 3 posts per call) ──
    TaskSpec(
        task_id="transpose",
        display_name="Transpose — 3 posts per call",
        description="Consolidated generation: produces 3 posts per call using transpose.txt with pre-commit declarations. Used in lean mode for both A and B batches.",
        call_site="src/batch/pack_generator.py:transpose",
        default_purpose="generation",
        quality_tier="heavy",
        frequency="per_source",
        default_temperature=0.5,
        default_max_tokens=12000,
        default_thinking_budget=14000,
    ),
    # ── Blog / Narrative tasks ──
    TaskSpec(
        task_id="keyword_research",
        display_name="SEO keyword research",
        description="Identifies primary keyword, long-tail variations, related entities, PAA targets, and competition format for a blog topic.",
        call_site="src/blog/seo_research.py:keyword_research",
        default_purpose="prep",
        quality_tier="medium",
        frequency="per_batch",
        default_temperature=0.3,
        default_max_tokens=3000,
    ),
    TaskSpec(
        task_id="serp_analysis",
        display_name="SERP competition analysis",
        description="Analyzes likely top-10 competitors for primary keyword and identifies structural requirements to outrank them.",
        call_site="src/blog/seo_research.py:serp_analysis",
        default_purpose="prep",
        quality_tier="medium",
        frequency="per_batch",
        default_temperature=0.3,
        default_max_tokens=3000,
    ),
    TaskSpec(
        task_id="blog_topic_discovery",
        display_name="Blog topic discovery",
        description="Combines founder graph beliefs with web search to find high-relevance trending topics for blog posts.",
        call_site="src/blog/topic_discovery.py:discover_topics",
        default_purpose="prep",
        quality_tier="medium",
        frequency="per_batch",
        web_search=True,
        default_temperature=0.3,
        default_max_tokens=3000,
    ),
    TaskSpec(
        task_id="blog_outline",
        display_name="Blog outline generation",
        description="Creates structured blog outline with intro, sections, and conclusion from topic + founder context.",
        call_site="src/blog/outline_generator.py:generate_outline",
        default_purpose="generation",
        quality_tier="medium",
        frequency="per_batch",
        default_temperature=0.4,
        default_max_tokens=2000,
        default_thinking_budget=8000,
    ),
    TaskSpec(
        task_id="blog_section_draft",
        display_name="Blog section drafting",
        description="Writes one section of a blog post in founder voice with supporting beliefs and stories.",
        call_site="src/blog/section_drafter.py:draft_section",
        default_purpose="generation",
        quality_tier="heavy",
        frequency="per_post",
        default_temperature=0.5,
        default_max_tokens=4000,
        default_thinking_budget=12000,
    ),
    TaskSpec(
        task_id="blog_voice_check",
        display_name="Blog voice validation",
        description="Validates a complete blog post against founder voice markers, style rules, and vocabulary.",
        call_site="src/blog/voice_validator.py:validate_blog_voice",
        default_purpose="prep",
        quality_tier="medium",
        frequency="per_batch",
        default_temperature=0.3,
        default_max_tokens=3000,
        default_thinking_budget=10000,
    ),
    TaskSpec(
        task_id="blog_seo",
        display_name="Blog SEO optimization",
        description="Optimizes blog title, headings, and meta description for search engines.",
        call_site="src/blog/seo_optimizer.py:optimize_seo",
        default_purpose="prep",
        quality_tier="light",
        frequency="per_batch",
        default_temperature=0.2,
        default_max_tokens=1500,
    ),
    TaskSpec(
        task_id="narrative_transcript_analysis",
        display_name="Transcript analysis",
        description="Extracts themes, stories, quotes, and contrarian angles from podcast transcripts.",
        call_site="src/blog/transcript_analyzer.py:analyze_transcript",
        default_purpose="prep",
        quality_tier="medium",
        frequency="per_batch",
        default_temperature=0.3,
        default_max_tokens=8000,
        default_thinking_budget=10000,
    ),
    TaskSpec(
        task_id="narrative_mining",
        display_name="Narrative angle mining",
        description="Cross-references transcript themes with founder graph to identify publishable narrative angles.",
        call_site="src/blog/transcript_analyzer.py:mine_narratives",
        default_purpose="prep",
        quality_tier="medium",
        frequency="per_batch",
        default_temperature=0.3,
        default_max_tokens=3000,
        default_thinking_budget=8000,
    ),
    TaskSpec(
        task_id="narrative_draft",
        display_name="Narrative blog drafting",
        description="Generates a full blog post from a narrative angle using transcript content + founder voice.",
        call_site="src/blog/section_drafter.py:draft_narrative",
        default_purpose="prep",
        quality_tier="heavy",
        frequency="per_batch",
        default_temperature=0.5,
        default_max_tokens=8000,
        default_thinking_budget=14000,
    ),
    TaskSpec(
        task_id="narrative_extraction",
        display_name="Narrative Extraction Protocol",
        description="Extracts 5-8 paradigm-level insights from podcast transcripts with 5 orders of thinking (claim → implications → mechanism → uncomfortable extension → paradigm reframe).",
        call_site="src/blog/narrative_extractor.py:extract_narratives",
        default_purpose="prep",
        quality_tier="heavy",
        frequency="per_batch",
        default_temperature=0.4,
        default_max_tokens=16000,
        default_thinking_budget=14000,
    ),
    # ── Studio utility tasks ──
    TaskSpec(
        task_id="transcript_structure",
        display_name="Transcript structuring",
        description="Cleans raw YouTube/podcast captions into well-structured JSON with proper sentences, speaker labels, and topic segments.",
        call_site="src/blog/youtube_transcript.py:structure_transcript",
        default_purpose="prep",
        quality_tier="light",
        frequency="conditional",
        default_temperature=0.2,
        default_max_tokens=16000,
    ),
]


TASK_CATALOG: dict[str, TaskSpec] = {t.task_id: t for t in _RAW_TASKS}
TASK_IDS: list[str] = [t.task_id for t in _RAW_TASKS]


def validate_task_id(task_id: str) -> bool:
    return task_id in TASK_CATALOG


def tasks_by_tier() -> dict[Tier, list[TaskSpec]]:
    out: dict[Tier, list[TaskSpec]] = {"heavy": [], "medium": [], "light": []}
    for t in _RAW_TASKS:
        out[t.quality_tier].append(t)
    return out


def task_catalog_dict() -> list[dict]:
    """Serialised form for the admin UI catalog endpoint."""
    return [
        {
            "task_id": t.task_id,
            "display_name": t.display_name,
            "description": t.description,
            "call_site": t.call_site,
            "default_purpose": t.default_purpose,
            "quality_tier": t.quality_tier,
            "frequency": t.frequency,
            "streaming": t.streaming,
            "web_search": t.web_search,
            "default_temperature": t.default_temperature,
            "default_max_tokens": t.default_max_tokens,
            "default_thinking_budget": t.default_thinking_budget,
        }
        for t in _RAW_TASKS
    ]
