"""Narrative session orchestrator — generates blog posts from podcast transcripts."""

from __future__ import annotations

import logging
import sys
import threading

from ..llm.task_router import LLMRouter
from ..generation.pipeline_events import PipelineEvent, PipelineEventBus
from ..batch.corpus_reader import load_founder_state, internalize_corpus, calibration_check
from ..batch.tracer import BatchTracer
from .state import NarrativeState
from .transcript_analyzer import analyze_transcript, mine_narratives
from .narrative_extractor import extract_narratives
from .seo_research import keyword_research, serp_analysis
from .section_drafter import draft_narrative
from .voice_validator import validate_blog_voice
from .seo_optimizer import optimize_seo
from .compiler import compile_blog, save_blog

logger = logging.getLogger(__name__)


class NarrativeSession:
    """Orchestrates narrative blog generation from transcript content."""

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
            from .session import CancelledError
            raise CancelledError("Narrative generation cancelled by user")

    def _emit(self, stage: str, status: str, data: dict | None = None, progress: float = 0.0):
        self._llm_stage = stage
        self._llm_progress = progress
        if status == "started":
            self._llm_text_buf = ""
        if self.event_bus:
            self.event_bus.emit_simple(stage, status, data or {}, progress)
        msg = f"[narrative] {stage}: {status}"
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

    def analyze(
        self,
        founder_slug: str,
        config_path: str = "config/llm-config.yaml",
        override_transcript: str | None = None,
    ) -> dict:
        """Analyze transcripts and return narrative angles (transcript-first, no graph)."""
        router = LLMRouter(config_path=config_path, founder_slug=founder_slug)
        router.set_on_token(self._on_llm_token)

        batch_state = load_founder_state(founder_slug, "linkedin")
        if override_transcript:
            transcript_text = override_transcript
        else:
            transcript_text = batch_state.raw_data.get("transcripts", "")

        if not transcript_text:
            return {"error": "No transcripts found for this founder", "angles": []}

        founder_ctx = batch_state.founder_ctx if batch_state else {}
        personality_card = batch_state.personality_card if batch_state else ""

        state = NarrativeState(
            founder_slug=founder_slug,
            transcript_text=transcript_text,
            llm_router=router,
            founder_ctx=founder_ctx,
            personality_card=personality_card,
        )

        llm = router.for_task("narrative_transcript_analysis")
        analysis = analyze_transcript(llm, state)

        # Derive a topic from top theme for keyword research
        themes = analysis.get("themes", [])
        if themes and isinstance(themes[0], dict):
            state.topic = themes[0].get("theme", "")

        if state.topic:
            keyword_research(llm, state)
            serp_analysis(llm, state)

        angles = mine_narratives(llm, state, analysis)

        self._check_cancel()
        self._emit("narrative_extraction", "started", progress=0.7)
        extraction = extract_narratives(llm, state)
        self._emit("narrative_extraction", "completed", {
            "narratives_found": len(extraction.get("narratives", [])),
        }, progress=0.9)

        return {
            "transcript_length": len(transcript_text),
            "analysis": analysis,
            "angles": angles,
            "narratives": extraction.get("narratives", []),
            "quality_note": extraction.get("quality_note", ""),
            "seo_inputs": state.seo_inputs,
        }

    def run(
        self,
        founder_slug: str,
        narrative_angle: str,
        format_type: str = "thought_leadership",
        tone: str = "conversational",
        target_word_count: int = 1500,
        config_path: str = "config/llm-config.yaml",
        override_transcript: str | None = None,
        use_founder_voice: bool = True,
        custom_instructions: str = "",
        narrative_angles: list[str] | None = None,
    ) -> dict:
        """Run the full narrative blog generation pipeline."""
        router = LLMRouter(config_path=config_path, founder_slug=founder_slug)
        router.set_on_token(self._on_llm_token)
        llm_gen = router.for_task("narrative_draft")

        tracer = BatchTracer(
            model=getattr(llm_gen, '_model_name', 'unknown'),
            provider=getattr(llm_gen, '_provider_name', 'unknown'),
        )

        # Phase 1: Load founder data (conditionally)
        self._check_cancel()
        self._emit("internalize", "started", progress=0.0)

        batch_state = load_founder_state(founder_slug, "linkedin")
        transcript_text = override_transcript or batch_state.raw_data.get("transcripts", "")

        if not transcript_text:
            self._emit("error", "pipeline_done", {"error": "No transcripts found"}, progress=1.0)
            if self.event_bus:
                self.event_bus.close()
            return {"error": "No transcripts found for this founder"}

        if use_founder_voice:
            internalization = internalize_corpus(llm_gen, batch_state)
            batch_state.founder_internalization = internalization
            batch_state.voice_markers = internalization.get("voice_markers", [])
            batch_state.formatting_habits = internalization.get("formatting_habits", {})
            cal = calibration_check(llm_gen, batch_state)
            batch_state.calibration_paragraph = cal.get("calibration_paragraph", "")
        else:
            logger.info("[narrative] Founder voice OFF — skipping internalize + calibration")
            batch_state.founder_internalization = {}
            batch_state.voice_markers = []
            batch_state.formatting_habits = {}
            batch_state.calibration_paragraph = ""

        combined_angle = narrative_angle
        if narrative_angles:
            all_angles = [narrative_angle] + [a for a in narrative_angles if a != narrative_angle]
            combined_angle = " | ".join(all_angles)

        state = NarrativeState(
            founder_slug=founder_slug,
            topic=combined_angle,
            tone=tone,
            target_words=(max(500, target_word_count - 500), target_word_count),
            format_type=format_type,
            transcript_text=transcript_text,
            custom_instructions=custom_instructions,
            founder_internalization=batch_state.founder_internalization,
            voice_markers=batch_state.voice_markers,
            formatting_habits=batch_state.formatting_habits,
            calibration_paragraph=batch_state.calibration_paragraph,
            personality_card=batch_state.personality_card if use_founder_voice else "",
            founder_ctx=batch_state.founder_ctx if use_founder_voice else {},
            raw_data=batch_state.raw_data,
            tracer=tracer,
            llm_router=router,
        )

        self._emit("internalize", "completed", {
            "voice_markers": len(state.voice_markers),
            "transcript_length": len(transcript_text),
            "founder_voice": use_founder_voice,
        }, progress=0.1)

        # Phase 2: Analyze transcript
        self._check_cancel()
        self._emit("transcript_analysis", "started", progress=0.1)
        analysis = analyze_transcript(llm_gen, state)
        self._emit("transcript_analysis", "completed", {
            "themes": len(analysis.get("themes", [])),
            "quotes": len(analysis.get("quotes", [])),
        }, progress=0.2)

        # Phase 3: Keyword research + SERP analysis
        self._check_cancel()
        themes = analysis.get("themes", [])
        if themes and isinstance(themes[0], dict) and not state.topic:
            state.topic = themes[0].get("theme", narrative_angle)

        self._emit("keyword_research", "started", progress=0.2)
        keyword_research(llm_gen, state)
        self._emit("keyword_research", "completed", {
            "primary_keyword": state.seo_inputs.get("primary_keyword", ""),
        }, progress=0.25)

        self._check_cancel()
        self._emit("serp_analysis", "started", progress=0.25)
        serp_analysis(llm_gen, state)
        self._emit("serp_analysis", "completed", {
            "recommended_format": state.serp_competition.get("recommended_format", ""),
        }, progress=0.3)

        # Phase 4: Mine narrative angles
        self._check_cancel()
        self._emit("narrative_mining", "started", progress=0.3)
        angles = mine_narratives(llm_gen, state, analysis)

        # Select the matching angle or first one
        selected = None
        for a in angles:
            if isinstance(a, dict) and narrative_angle.lower() in a.get("angle", "").lower():
                selected = a
                break
        if not selected and angles:
            selected = angles[0]
        if not selected:
            selected = {
                "angle": combined_angle,
                "format_recommendation": format_type,
                "supporting_transcript_quotes": [],
            }
        state.selected_angle = selected

        self._emit("narrative_mining", "completed", {
            "angles_found": len(angles),
            "selected": selected.get("angle", ""),
        }, progress=0.35)

        # Phase 5: Draft the full post
        self._check_cancel()
        self._emit("draft", "started", progress=0.35)
        draft_result = draft_narrative(llm_gen, state)

        title = draft_result.get("title", narrative_angle)
        content = draft_result.get("content", "")
        state.outline = {"title": title, "sections": [], "intro_hook": "", "conclusion_cta": ""}
        state.sections = [content]

        self._emit("draft", "completed", {
            "word_count": len(content.split()),
        }, progress=0.6)

        # Phase 6: Voice validation (skip if no founder voice)
        self._check_cancel()
        self._emit("voice_check", "started", progress=0.6)
        if use_founder_voice:
            validation = validate_blog_voice(llm_gen, content, state)
        else:
            validation = {"overall": "SKIP", "voice_marker_score": 0, "note": "Founder voice disabled"}
        state.voice_validation = validation
        self._emit("voice_check", "completed", {
            "overall": validation.get("overall", "PASS"),
            "voice_score": validation.get("voice_marker_score", 0),
        }, progress=0.8)

        # Phase 7: SEO audit
        self._check_cancel()
        self._emit("seo_optimize", "started", progress=0.8)
        seo = optimize_seo(llm_gen, content, state)
        self._emit("seo_optimize", "completed", {
            "seo_title": seo.get("seo_title", ""),
        }, progress=0.9)

        # Phase 8: Compile
        self._check_cancel()
        self._emit("compile", "started", progress=0.9)
        markdown = compile_blog(state)
        blog_id = save_blog(state)
        word_count = len(markdown.split())
        self._emit("compile", "completed", {
            "blog_id": blog_id,
            "word_count": word_count,
        }, progress=0.95)

        result = {
            "blog_id": blog_id,
            "title": state.seo_data.get("seo_title") or title,
            "topic": narrative_angle,
            "format_type": format_type,
            "tone": tone,
            "word_count": word_count,
            "voice_validation": validation,
            "seo_data": state.seo_data,
            "markdown": markdown,
        }

        self._emit("narrative", "pipeline_done", {
            "blog_id": blog_id,
            "word_count": word_count,
        }, progress=1.0)

        if self.event_bus:
            self.event_bus.close()

        return result
