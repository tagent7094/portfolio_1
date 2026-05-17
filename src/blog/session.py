"""Blog session orchestrator — runs the full blog generation pipeline."""

from __future__ import annotations

import logging
import sys
import threading

from ..llm.task_router import LLMRouter
from ..generation.pipeline_events import PipelineEvent, PipelineEventBus
from ..batch.corpus_reader import load_founder_state, internalize_corpus, calibration_check
from ..batch.tracer import BatchTracer
from .state import BlogState
from .topic_discovery import discover_topics
from .seo_research import keyword_research, serp_analysis
from .outline_generator import generate_outline
from .section_drafter import draft_section
from .voice_validator import validate_blog_voice
from .seo_optimizer import optimize_seo
from .compiler import compile_blog, save_blog

logger = logging.getLogger(__name__)


class CancelledError(Exception):
    pass


class BlogSession:
    """Orchestrates the full blog generation pipeline."""

    def __init__(self, event_bus: PipelineEventBus | None = None):
        self.event_bus = event_bus
        self.cancel_event = threading.Event()
        self._llm_text_buf = ""
        self._llm_stage = ""
        self._llm_progress = 0.0
        self._LLM_FLUSH_CHARS = 500
        self._LLM_MAX_WINDOW = 2000

    def _check_cancel(self):
        if self.cancel_event.is_set():
            raise CancelledError("Blog generation cancelled by user")

    def _emit(self, stage: str, status: str, data: dict | None = None, progress: float = 0.0):
        self._llm_stage = stage
        self._llm_progress = progress
        if status == "started":
            self._llm_text_buf = ""
        if self.event_bus:
            self.event_bus.emit_simple(stage, status, data or {}, progress)
        msg = f"[blog] {stage}: {status}"
        if data:
            msg += f" {data}"
        print(msg, file=sys.stderr, flush=True)

    def _on_llm_token(self, text: str):
        self._llm_text_buf += text
        if len(self._llm_text_buf) >= self._LLM_FLUSH_CHARS and self.event_bus:
            window = self._llm_text_buf[-self._LLM_MAX_WINDOW:]
            self.event_bus.emit(PipelineEvent(
                stage=self._llm_stage,
                status="llm_chunk",
                progress=self._llm_progress,
                llm_text=window,
            ))
            self._llm_text_buf = window

    def run(
        self,
        founder_slug: str,
        topic: str,
        tone: str = "conversational",
        target_word_count: int = 1500,
        seo_focus: bool = True,
        config_path: str = "config/llm-config.yaml",
        custom_instructions: str = "",
        source_documents_text: str = "",
        source_document_names: list | None = None,
        podcast_transcripts_text: str = "",
        podcast_names: list | None = None,
        generation_mode: str = "auto",
    ) -> dict:
        """Run the full blog generation pipeline."""
        router = LLMRouter(config_path=config_path, founder_slug=founder_slug)
        router.set_on_token(self._on_llm_token)
        llm_gen = router.for_task("blog_section_draft")

        tracer = BatchTracer(
            model=getattr(llm_gen, '_model_name', 'unknown'),
            provider=getattr(llm_gen, '_provider_name', 'unknown'),
        )

        # Phase 1: Load founder data + internalization (reuses batch pipeline)
        self._check_cancel()
        self._emit("internalize", "started", progress=0.0)

        batch_state = load_founder_state(founder_slug, "linkedin")
        internalization = internalize_corpus(llm_gen, batch_state)
        batch_state.founder_internalization = internalization
        batch_state.voice_markers = internalization.get("voice_markers", [])
        batch_state.formatting_habits = internalization.get("formatting_habits", {})

        # Calibration
        cal = calibration_check(llm_gen, batch_state)
        batch_state.calibration_paragraph = cal.get("calibration_paragraph", "")

        combined_docs = source_documents_text or ""
        if podcast_transcripts_text:
            combined_docs = (combined_docs + "\n\n--- PODCAST TRANSCRIPTS ---\n\n" + podcast_transcripts_text) if combined_docs else podcast_transcripts_text

        state = BlogState(
            founder_slug=founder_slug,
            topic=topic,
            tone=tone,
            target_words=(max(500, target_word_count - 500), target_word_count),
            founder_internalization=batch_state.founder_internalization,
            voice_markers=batch_state.voice_markers,
            formatting_habits=batch_state.formatting_habits,
            calibration_paragraph=batch_state.calibration_paragraph,
            personality_card=batch_state.personality_card,
            founder_ctx=batch_state.founder_ctx,
            raw_data=batch_state.raw_data,
            tracer=tracer,
            llm_router=router,
            custom_instructions=custom_instructions,
            source_documents_text=combined_docs,
            source_document_names=source_document_names or [],
            podcast_transcripts_text=podcast_transcripts_text,
            podcast_names=podcast_names or [],
            generation_mode=generation_mode,
        )

        self._emit("internalize", "completed", {
            "voice_markers": len(state.voice_markers),
        }, progress=0.1)

        # Phase 2: Topic discovery (skip if user provided instructions + topic)
        self._check_cancel()
        if not topic and generation_mode != "instructed":
            self._emit("topic_discovery", "started", progress=0.1)
            topics = discover_topics(llm_gen, state, n_topics=10)
            if topics:
                state.topic = topics[0].get("topic", "")
                topic = state.topic
            self._emit("topic_discovery", "completed", {
                "topics_found": len(topics),
                "selected": state.topic,
            }, progress=0.2)
        else:
            if not topic and custom_instructions:
                state.topic = custom_instructions[:100]
                topic = state.topic
            self._emit("topic_discovery", "completed", {
                "topics_found": 0,
                "selected": topic,
            }, progress=0.2)

        # Phase 3: Keyword research
        self._check_cancel()
        self._emit("keyword_research", "started", progress=0.2)
        seo_inputs = keyword_research(llm_gen, state)
        self._emit("keyword_research", "completed", {
            "primary_keyword": seo_inputs.get("primary_keyword", ""),
        }, progress=0.25)

        # Phase 4: SERP analysis
        self._check_cancel()
        self._emit("serp_analysis", "started", progress=0.25)
        serp = serp_analysis(llm_gen, state)
        self._emit("serp_analysis", "completed", {
            "recommended_format": serp.get("recommended_format", ""),
        }, progress=0.3)

        # Phase 5: Generate outline
        self._check_cancel()
        self._emit("outline", "started", progress=0.3)
        outline = generate_outline(llm_gen, state)
        self._emit("outline", "completed", {
            "title": outline.get("title", ""),
            "sections": len(outline.get("sections", [])),
        }, progress=0.4)

        # Phase 6: Draft sections
        sections = outline.get("sections", [])
        drafted_sections: list[str] = []
        for i, section in enumerate(sections):
            self._check_cancel()
            progress = 0.4 + (i / max(len(sections), 1)) * 0.3
            self._emit(f"section_{i+1}", "started", {
                "heading": section.get("heading", ""),
            }, progress=progress)

            text = draft_section(llm_gen, section, i, state, drafted_sections)
            drafted_sections.append(text)

            self._emit(f"section_{i+1}", "completed", {
                "word_count": len(text.split()),
            }, progress=progress + 0.3 / max(len(sections), 1))

        state.sections = drafted_sections

        # Phase 7: Voice validation
        self._check_cancel()
        self._emit("voice_check", "started", progress=0.75)
        full_text = "\n\n".join(drafted_sections)
        validation = validate_blog_voice(llm_gen, full_text, state)
        state.voice_validation = validation
        self._emit("voice_check", "completed", {
            "overall": validation.get("overall", "PASS"),
            "voice_score": validation.get("voice_marker_score", 0),
        }, progress=0.85)

        # Phase 8: SEO audit
        self._check_cancel()
        if seo_focus:
            self._emit("seo_optimize", "started", progress=0.85)
            seo = optimize_seo(llm_gen, full_text, state)
            self._emit("seo_optimize", "completed", {
                "seo_title": seo.get("seo_title", ""),
                "should_publish": seo.get("publication_decision", {}).get("should_publish", True),
            }, progress=0.9)
        else:
            state.seo_data = {"seo_title": outline.get("title", topic)}

        # Phase 9: Compile and save
        self._check_cancel()
        self._emit("compile", "started", progress=0.9)
        markdown = compile_blog(state)
        blog_id = save_blog(state)
        word_count = len(markdown.split())
        self._emit("compile", "completed", {
            "blog_id": blog_id,
            "word_count": word_count,
        }, progress=0.95)

        # Done
        result = {
            "blog_id": blog_id,
            "title": state.seo_data.get("seo_title") or outline.get("title", topic),
            "topic": state.topic,
            "tone": state.tone,
            "word_count": word_count,
            "voice_validation": validation,
            "seo_data": state.seo_data,
            "markdown": markdown,
        }

        self._emit("blog", "pipeline_done", {
            "blog_id": blog_id,
            "word_count": word_count,
        }, progress=1.0)

        if self.event_bus:
            self.event_bus.close()

        return result
