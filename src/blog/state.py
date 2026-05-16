"""State objects for blog and narrative generation pipelines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..batch.tracer import BatchTracer


@dataclass
class BlogState:
    founder_slug: str
    platform: str = "blog"
    topic: str = ""
    tone: str = "conversational"
    target_words: tuple[int, int] = (1000, 2500)

    # Populated during pipeline
    founder_internalization: dict = field(default_factory=dict)
    voice_markers: list[str] = field(default_factory=list)
    formatting_habits: dict = field(default_factory=dict)
    calibration_paragraph: str = ""
    personality_card: str = ""
    founder_ctx: dict = field(default_factory=dict)
    raw_data: dict = field(default_factory=dict)
    web_search_context: dict = field(default_factory=dict)

    # v2: Source material & instructions
    custom_instructions: str = ""
    source_documents_text: str = ""
    source_document_names: list[str] = field(default_factory=list)
    podcast_transcripts_text: str = ""
    podcast_names: list[str] = field(default_factory=list)
    generation_mode: str = "auto"

    # Pipeline outputs
    discovered_topics: list[dict] = field(default_factory=list)
    outline: dict = field(default_factory=dict)
    sections: list[dict] = field(default_factory=list)
    seo_data: dict = field(default_factory=dict)
    voice_validation: dict = field(default_factory=dict)
    final_markdown: str = ""
    blog_id: str = ""

    # Infrastructure (set by session, not serialized)
    tracer: BatchTracer | None = field(default=None, repr=False)
    llm_router: object | None = field(default=None, repr=False)


@dataclass
class NarrativeState(BlogState):
    transcript_text: str = ""
    narrative_angles: list[dict] = field(default_factory=list)
    selected_angle: dict = field(default_factory=dict)
    format_type: str = "thought_leadership"
