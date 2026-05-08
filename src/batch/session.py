"""Batch session orchestrator — top-level runner for the full 10-source pipeline."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from ..llm.factory import create_llm
from ..llm.base import LLMProvider
from ..generation.pipeline_events import PipelineEvent, PipelineEventBus
from .state import BatchState
from .tracer import BatchTracer
from .corpus_reader import load_founder_state, internalize_corpus, calibration_check
from .source_selector import select_sources
from .pack_generator import generate_pack
from .amplifier import amplify_post, convergence_test
from .compiler import compile_json, save_output

logger = logging.getLogger(__name__)


class BatchSession:
    """Orchestrates the full batch post generation pipeline."""

    def __init__(self, event_bus: PipelineEventBus | None = None):
        self.event_bus = event_bus

    def _emit(self, stage: str, status: str, data: dict | None = None, progress: float = 0.0):
        if self.event_bus:
            self.event_bus.emit_simple(stage, status, data or {}, progress)
        msg = f"[batch] {stage}: {status}"
        if data:
            msg += f" {data}"
        print(msg, file=sys.stderr, flush=True)

    def run(
        self,
        founder_slug: str,
        platform: str = "linkedin",
        creativity: float = 0.5,
        n_sources: int = 10,
        source_posts: list[str] | None = None,
        config_path: str = "config/llm-config.yaml",
    ) -> dict:
        """Run the full batch generation pipeline."""
        llm = create_llm(config_path=config_path, purpose="generation")

        tracer = BatchTracer(
            model=getattr(llm, '_model_name', 'unknown'),
            provider=getattr(llm, '_provider_name', 'unknown'),
        )

        # Phase 1: Load founder data + deep internalization
        self._emit("internalize", "started", progress=0.0)
        state = load_founder_state(founder_slug, platform)
        state.creativity = creativity
        state.tracer = tracer

        tracer.trace_step("load_founder", f"Loaded founder data for {founder_slug}")

        internalization = internalize_corpus(llm, state)
        state.founder_internalization = internalization
        state.voice_markers = internalization.get("voice_markers", [])
        state.formatting_habits = internalization.get("formatting_habits", {})

        if internalization.get("word_count_range"):
            wc = internalization["word_count_range"]
            if isinstance(wc, list) and len(wc) == 2:
                state.word_count_range = (int(wc[0]), int(wc[1]))

        if internalization.get("median_word_count"):
            state.median_word_count = int(internalization["median_word_count"])

        self._emit("internalize", "completed", {
            "tensions": len(internalization.get("tensions", [])),
            "scenes": len(internalization.get("signature_scenes", [])),
            "voice_markers": len(state.voice_markers),
            "word_count_range": list(state.word_count_range),
        }, progress=0.05)

        # Calibration check
        self._emit("calibration", "started", progress=0.07)
        cal = calibration_check(llm, state)
        tracer.trace_decision(
            "calibration",
            f"confidence={cal.get('confidence', 'unknown')}",
            metadata={"critique": cal.get("self_critique", "")},
        )
        self._emit("calibration", "completed", {
            "confidence": cal.get("confidence", "unknown"),
            "critique": cal.get("self_critique", ""),
        }, progress=0.1)

        # Phase 2: Web search enrichment (if Anthropic provider)
        self._emit("web_search", "started", progress=0.1)
        web_context = self._web_search_enrich(llm, state)
        state.web_search_context = web_context
        self._emit("web_search", "completed", {
            "searches": len(web_context.get("searches", [])),
            "topics_found": len(web_context.get("trending_topics", [])),
        }, progress=0.12)

        # Phase 3: Select sources
        self._emit("select_sources", "started", progress=0.12)
        state.source_posts = select_sources(llm, state, n_sources, source_posts)
        self._emit("select_sources", "completed", {
            "count": len(state.source_posts),
        }, progress=0.15)

        # Phase 4: Generate packs sequentially
        total = len(state.source_posts)
        for i, source in enumerate(state.source_posts):
            pack_num = i + 1

            # Memory refresh at midpoint
            if i == 5 and total >= 8:
                self._emit("memory_refresh", "started", progress=0.15 + (i / total) * 0.75)
                refresh = internalize_corpus(llm, state)
                state.founder_internalization.update(refresh)
                if refresh.get("voice_markers"):
                    state.voice_markers = refresh["voice_markers"]
                self._emit("memory_refresh", "completed", progress=0.15 + (i / total) * 0.75)

            pack_progress_base = 0.15 + (i / total) * 0.75
            self._emit(f"pack_{pack_num}", "started", {
                "source_preview": source[:100],
            }, progress=pack_progress_base)

            def pack_callback(sub_stage, data):
                self._emit(f"pack_{pack_num}", "progress", {sub_stage: data})

            pack = generate_pack(llm, source, pack_num, state, event_callback=pack_callback)

            # Amplifier pass on each post
            amplified_posts = []
            for j, post in enumerate(pack.posts):
                post = amplify_post(llm, post, amplified_posts, state)
                amplified_posts.append(post)
                state.arguments_compressed.append(post.argument_compressed)

            # Convergence test
            conv = convergence_test(llm, amplified_posts, source[:200], state)
            pack.convergence_test = conv
            pack.posts = amplified_posts
            state.packs.append(pack)

            tracer.trace_decision(
                f"pack_{pack_num}_complete",
                f"convergence={'PASS' if conv.get('passed', True) else 'FAIL'}",
                metadata={"posts": len(pack.posts), "recommendation": conv.get("recommendation", "")},
            )

            self._emit(f"pack_{pack_num}", "completed", {
                "posts": len(pack.posts),
                "convergence": conv.get("passed", True),
            }, progress=pack_progress_base + (0.75 / total))

        # Phase 5: Compile output
        self._emit("compile", "started", progress=0.9)
        output = compile_json(state)
        filepath = save_output(output, state)
        self._emit("compile", "completed", {
            "total_posts": output["metadata"]["total_posts"],
            "filepath": filepath,
        }, progress=0.95)

        # Done
        self._emit("batch", "pipeline_done", {
            "total_posts": output["metadata"]["total_posts"],
            "filepath": filepath,
        }, progress=1.0)

        if self.event_bus:
            self.event_bus.close()

        return output

    def _web_search_enrich(self, llm: LLMProvider, state: BatchState) -> dict:
        """Use web search to find trending topics and facts in founder's domain."""
        if not hasattr(llm, 'generate_with_search'):
            return {"searches": [], "trending_topics": [], "facts": []}

        beliefs = state.founder_ctx.get("beliefs", [])[:5]
        domains = [b.get("topic", "") for b in beliefs if b.get("topic")]
        if not domains:
            return {"searches": [], "trending_topics": [], "facts": []}

        domain_str = ", ".join(domains[:3])
        prompt = f"""You are researching current trends and facts for a thought leader who writes about: {domain_str}

Search the web for:
1. Trending topics or recent news in these areas
2. Recent statistics or data points that could strengthen arguments
3. Contrarian viewpoints gaining traction

After searching, summarize your findings as JSON:
```json
{{
  "trending_topics": ["topic1", "topic2", ...],
  "facts": [
    {{"fact": "...", "source": "...", "relevance": "..."}},
    ...
  ],
  "contrarian_angles": ["angle1", "angle2", ...]
}}
```"""

        import time as _t
        _start = _t.time()
        result = llm.generate_with_search(
            prompt,
            system_prompt="You are a research assistant. Search the web and provide factual, current information.",
            temperature=0.3,
            max_tokens=2000,
            max_searches=3,
        )
        _dur = int((_t.time() - _start) * 1000)

        for s in result.get("searches", []):
            state.tracer.trace_web_search(
                stage="web_search_enrich",
                query=s.get("query", ""),
                results=s.get("results", []),
                duration_ms=_dur // max(len(result.get("searches", [])), 1),
            )

        from ..utils.json_parser import parse_llm_json
        parsed = parse_llm_json(result.get("text", ""))
        if not isinstance(parsed, dict):
            parsed = {}

        parsed["searches"] = result.get("searches", [])

        state.tracer.trace_step(
            "web_search_complete",
            f"Found {len(parsed.get('trending_topics', []))} topics, {len(parsed.get('facts', []))} facts",
            duration_ms=_dur,
        )

        return parsed


def run_batch_cli(
    founder_slug: str,
    n_sources: int = 10,
    creativity: float = 0.5,
    platform: str = "linkedin",
):
    """CLI entry point for batch generation."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    session = BatchSession()
    output = session.run(
        founder_slug=founder_slug,
        platform=platform,
        creativity=creativity,
        n_sources=n_sources,
    )
    total = output["metadata"]["total_posts"]
    print(f"\nBatch complete: {total} posts generated across {len(output['packs'])} packs.")
    return output


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Batch post generation")
    parser.add_argument("--founder", required=True, help="Founder slug")
    parser.add_argument("--sources", type=int, default=10, help="Number of source posts")
    parser.add_argument("--creativity", type=float, default=0.5, help="Creativity level 0.0-1.0")
    parser.add_argument("--platform", default="linkedin", help="Target platform")
    args = parser.parse_args()

    run_batch_cli(args.founder, args.sources, args.creativity, args.platform)
