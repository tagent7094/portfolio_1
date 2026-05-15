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


_RAW_TASKS: list[TaskSpec] = [
    TaskSpec(
        task_id="internalize",
        display_name="Founder voice internalization",
        description="Deep corpus reading — extracts voice markers, scenes, tensions, formatting habits. Runs once per batch (plus a midpoint refresh on long runs).",
        call_site="src/batch/corpus_reader.py:internalize_corpus",
        default_purpose="generation",
        quality_tier="heavy",
        frequency="per_batch",
        default_temperature=0.3,
        default_max_tokens=16000,
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
        default_max_tokens=1000,
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
        default_max_tokens=4000,
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
        default_max_tokens=2000,
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
        default_max_tokens=3000,
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
        default_max_tokens=3000,
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
        default_max_tokens=2000,
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
        default_max_tokens=2000,
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
        default_max_tokens=3000,
    ),
    TaskSpec(
        task_id="amplifier_diagnose",
        display_name="Opening line diagnosis (7-gate)",
        description="Runs the 7-gate opener diagnosis on every post, including the source_mirror gate for Batch A.",
        call_site="src/batch/amplifier.py:diagnose_opener",
        default_purpose="prep",
        quality_tier="medium",
        frequency="per_post",
        default_temperature=0.2,
        default_max_tokens=4000,
    ),
    TaskSpec(
        task_id="amplifier_generate",
        display_name="Opening line alternatives (×5)",
        description="Generates 5 alternative openings per post (variants A-E) for amplification.",
        call_site="src/batch/amplifier.py:generate_alternatives",
        default_purpose="generation",
        quality_tier="heavy",
        frequency="per_post",
        default_temperature=0.5,
        default_max_tokens=4000,
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
        default_max_tokens=1000,
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
        }
        for t in _RAW_TASKS
    ]
