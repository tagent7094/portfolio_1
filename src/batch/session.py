"""Batch session orchestrator — top-level runner for the full 10-source pipeline."""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path

from ..llm.factory import create_llm
from ..llm.base import LLMProvider
from ..llm.task_router import LLMRouter
from ..generation.pipeline_events import PipelineEvent, PipelineEventBus
from .state import BatchState
from .tracer import BatchTracer
from .corpus_reader import load_founder_state, internalize_corpus, calibration_check
from .source_selector import select_sources
from .pack_generator import generate_pack, _generate_pack_lean, _enforce_word_count
from .amplifier import amplify_post_v2, amplify_batch_v2, convergence_test
from .voice_validator import validate_voice, regenerate_with_voice_override
from .compiler import compile_json, save_output
from .exclusion_scanner import load_exclusions, scan_for_exclusions
from .saturation import check_saturation

logger = logging.getLogger(__name__)


class CancelledError(Exception):
    pass


def _split_recommendation_into_angles(recommendation: str) -> list[str]:
    """Parse a convergence recommendation into discrete diversity angles.

    The convergence LLM typically returns recommendations like:
      "Request posts that argue different takes, such as: (1) angle one;
       (2) angle two; (3) angle three; (4) angle four"
    or sometimes "1. ... 2. ... 3. ..." or comma-separated phrases.

    Returns a list of angle strings. Each angle is fed into the regen prompt for a
    different overlapping post so they don't all converge again. Returns [] if
    nothing parseable.
    """
    if not recommendation or not isinstance(recommendation, str):
        return []
    import re as _re

    # Pattern 1: "(1) ... (2) ... (3) ..."
    paren_matches = _re.split(r"\s*\(\d+\)\s*", recommendation)
    if len(paren_matches) > 2:
        return [m.strip(" ;.,") for m in paren_matches[1:] if m.strip()]

    # Pattern 2: "1. ... 2. ... 3. ..." (numbered)
    num_matches = _re.split(r"(?:^|\s)\d+\.\s+", recommendation)
    if len(num_matches) > 2:
        return [m.strip(" ;.,") for m in num_matches[1:] if m.strip()]

    # Pattern 3: semicolon-separated after a colon ("such as: A; B; C")
    if ":" in recommendation:
        tail = recommendation.split(":", 1)[1]
        parts = [p.strip(" ;.,") for p in tail.split(";") if len(p.strip()) > 15]
        if len(parts) >= 2:
            return parts

    return []


class BatchSession:
    """Orchestrates the full batch post generation pipeline."""

    def __init__(self, event_bus: PipelineEventBus | None = None):
        self.event_bus = event_bus
        self.cancel_event = threading.Event()
        self._llm_text_buf = ""
        self._llm_stage = ""
        self._llm_progress = 0.0
        self._LLM_FLUSH_CHARS = 50
        self._LLM_MAX_WINDOW = 2000

    def _check_cancel(self):
        if self.cancel_event.is_set():
            raise CancelledError("Generation cancelled by user")

    def _emit(self, stage: str, status: str, data: dict | None = None, progress: float = 0.0):
        self._llm_stage = stage
        self._llm_progress = progress
        if status == "started":
            self._llm_text_buf = ""
        if self.event_bus:
            self.event_bus.emit_simple(stage, status, data or {}, progress)
        msg = f"[batch] {stage}: {status}"
        if data:
            msg += f" {data}"
        print(msg, file=sys.stderr, flush=True)

    def _on_llm_token(self, text: str):
        self._llm_text_buf += text
        if len(self._llm_text_buf) >= self._LLM_FLUSH_CHARS and self.event_bus:
            window = self._llm_text_buf[-self._LLM_MAX_WINDOW:]
            from src.generation.pipeline_events import PipelineEvent
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
        platform: str = "linkedin",
        creativity: float = 0.5,
        n_sources: int = 10,
        posts_per_source: int = 9,
        enable_thinking: bool = True,
        source_posts: list[str] | None = None,
        config_path: str = "config/llm-config.yaml",
        effort: str = "high",
        lean: bool = False,
    ) -> dict:
        """Run the full batch generation pipeline.

        Uses two models:
          - llm_gen (Opus): creative generation — internalization, post writing, opener alternatives
          - llm_prep (Haiku): analysis/classification — calibration, source selection, dissection,
            opener diagnosis, convergence testing
        """
        try:
            return self._run_pipeline(
                founder_slug=founder_slug,
                platform=platform,
                creativity=creativity,
                n_sources=n_sources,
                posts_per_source=posts_per_source,
                enable_thinking=enable_thinking,
                source_posts=source_posts,
                config_path=config_path,
                effort=effort,
                lean=lean,
            )
        except CancelledError:
            raise
        except Exception as exc:
            import traceback
            traceback.print_exc(file=sys.stderr)
            self._emit("batch", "pipeline_done", {
                "error": f"{type(exc).__name__}: {exc}",
                "total_posts": 0,
            }, progress=1.0)
            if self.event_bus:
                self.event_bus.close()
            raise

    def _run_pipeline(
        self,
        founder_slug: str,
        platform: str = "linkedin",
        creativity: float = 0.5,
        n_sources: int = 10,
        posts_per_source: int = 9,
        enable_thinking: bool = True,
        source_posts: list[str] | None = None,
        config_path: str = "config/llm-config.yaml",
        effort: str = "high",
        lean: bool = False,
    ) -> dict:
        # Task-aware LLM resolution. The router consults founder override →
        # admin default → llm-config.yaml fallback for every distinct pipeline
        # task. `llm_gen` and `llm_prep` are kept as back-compat handles for
        # callers that haven't been migrated to task-aware lookups yet.
        router = LLMRouter(config_path=config_path, founder_slug=founder_slug)
        router.set_on_token(self._on_llm_token)
        llm_gen = router.for_task("generate_a")
        llm_prep = router.for_task("dissect")

        if hasattr(llm_gen, 'enable_thinking'):
            llm_gen.enable_thinking = enable_thinking
        if hasattr(llm_gen, 'effort'):
            llm_gen.effort = effort

        tracer = BatchTracer(
            model=getattr(llm_gen, '_model_name', 'unknown'),
            provider=getattr(llm_gen, '_provider_name', 'unknown'),
        )
        tracer.start_log_capture()

        # Phase 1: Load founder data + deep internalization (Opus — creative)
        self._check_cancel()
        self._emit("internalize", "started", progress=0.0)
        state = load_founder_state(founder_slug, platform)
        state.creativity = creativity
        state.tracer = tracer
        state.llm_router = router
        state.lean_mode = lean

        state.exclusions = load_exclusions(founder_slug)
        tracer.trace_step("load_founder", f"Loaded founder data for {founder_slug}")
        tracer.trace_step("multi_model", f"gen={getattr(llm_gen, '_model_name', '?')}, prep={getattr(llm_prep, '_model_name', '?')}")

        if state.freshness_warning:
            self._emit("freshness_warning", state.freshness_warning, progress=0.01)
            tracer.trace_decision("freshness", state.freshness_warning)

        internalization = internalize_corpus(llm_gen, state)
        state.founder_internalization = internalization
        state.voice_markers = internalization.get("voice_markers", [])
        state.formatting_habits = internalization.get("formatting_habits", {})

        if internalization.get("word_count_range"):
            wc = internalization["word_count_range"]
            if isinstance(wc, list) and len(wc) == 2:
                a, b = int(wc[0]), int(wc[1])
                state.word_count_range = (min(a, b), max(a, b))

        if internalization.get("median_word_count"):
            state.median_word_count = int(internalization["median_word_count"])

        self._emit("internalize", "completed", {
            "tensions": len(internalization.get("tensions", [])),
            "scenes": len(internalization.get("signature_scenes", [])),
            "voice_markers": len(state.voice_markers),
            "word_count_range": list(state.word_count_range),
        }, progress=0.05)

        # Calibration check (Opus — creative voice synthesis)
        self._check_cancel()
        self._emit("calibration", "started", progress=0.07)
        cal = calibration_check(llm_gen, state)
        tracer.trace_decision(
            "calibration",
            f"confidence={cal.get('confidence', 'unknown')}",
            metadata={"critique": cal.get("self_critique", ""), "model": getattr(llm_gen, '_model_name', '?')},
        )
        state.calibration_paragraph = cal.get("calibration_paragraph", "")
        self._emit("calibration", "completed", {
            "confidence": cal.get("confidence", "unknown"),
            "critique": cal.get("self_critique", ""),
        }, progress=0.1)

        # Phase 2: Web search enrichment (Haiku — data retrieval)
        self._check_cancel()
        self._emit("web_search", "started", progress=0.1)
        web_context = self._web_search_enrich(llm_prep, state)
        state.web_search_context = web_context
        self._emit("web_search", "completed", {
            "searches": len(web_context.get("searches", [])),
            "search_queries": [s.get("query", "") for s in web_context.get("searches", [])],
            "trending_topics": web_context.get("trending_topics", []),
            "facts_count": len(web_context.get("facts", [])),
        }, progress=0.12)

        # Phase 3: Select sources (Haiku — ranking/classification)
        self._check_cancel()
        self._emit("select_sources", "started", progress=0.12)
        state.source_posts = select_sources(llm_prep, state, n_sources, source_posts)
        self._emit("select_sources", "completed", {
            "count": len(state.source_posts),
        }, progress=0.15)

        # Phase 4: Generate packs sequentially
        total = len(state.source_posts)
        for i, source in enumerate(state.source_posts):
            self._check_cancel()
            pack_num = i + 1

            # Memory refresh at midpoint (Opus — creative)
            if i == total // 2 and total >= 6:
                self._emit("memory_refresh", "started", progress=0.15 + (i / total) * 0.75)
                refresh = internalize_corpus(llm_gen, state)
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

            if state.lean_mode:
                pack = _generate_pack_lean(
                    llm_gen, source, pack_num, state,
                    posts_per_source=posts_per_source,
                    event_callback=pack_callback,
                    llm_prep=llm_prep,
                )
            else:
                pack = generate_pack(
                    llm_gen, source, pack_num, state,
                    posts_per_source=posts_per_source,
                    event_callback=pack_callback,
                    llm_prep=llm_prep,
                )

            # Voice validation pass (per-post via validate.txt — full 5 dimensions)
            self._emit(f"pack_{pack_num}", "progress", {"voice_validation": "starting"})
            validated_posts = []
            for j, post in enumerate(pack.posts):
                self._check_cancel()

                if post.batch == "A":
                    post.validation_result = {"overall": "SKIP", "reason": "batch_a_mirrored"}
                    post.voice_score = 3
                    logger.info("[batch] %s: Batch A — skipping voice validation (mirrored)", post.label)
                    validated_posts.append(post)
                    continue

                validation = validate_voice(llm_gen, post, state)
                post.validation_result = validation

                if validation.get("overall") == "FAIL":
                    tracer.trace_decision(
                        f"voice_validation_{post.label}",
                        f"FAIL: {validation.get('suggestion', '')}",
                        metadata=validation,
                    )
                    post = regenerate_with_voice_override(llm_gen, post, validation, state)
                    post = _enforce_word_count(post, state, llm=llm_gen)
                    reval = validate_voice(llm_gen, post, state)
                    post.voice_score = min(
                        reval.get("voice_marker_score", 3),
                        reval.get("register_score", 3),
                    )
                    post.validation_result = {**post.validation_result, "reval_score": post.voice_score}
                else:
                    post.voice_score = min(
                        validation.get("voice_marker_score", 3),
                        validation.get("register_score", 3),
                    )

                validated_posts.append(post)

            # Exclusion scan (flag only, don't reject)
            if state.exclusions:
                for post in validated_posts:
                    hits = scan_for_exclusions(post, state.exclusions)
                    if hits:
                        tracer.trace_decision(
                            f"exclusion_{post.label}",
                            f"Matched {len(hits)} exclusion(s): {', '.join(hits[:5])}",
                            metadata={"exclusions": hits},
                        )

            # Amplifier pass — Batch A skips, Batch B uses single batched call
            amplified_posts = []
            published_corpus = (
                state.raw_data.get("founder_posts_structured")
                or [{"text": p, "post_id": f"p_{i}"} for i, p in enumerate(
                    state.raw_data.get("founder_posts_sample", "").split("\n\n---\n\n")
                ) if p.strip()]
            )

            # Phase A: amplify A posts in ONE batched call (variants only, never replace)
            a_validated = []
            b_validated = []
            for post in validated_posts:
                if post.batch == "A":
                    a_validated.append(post)
                else:
                    b_validated.append(post)

            if a_validated:
                a_amplified = amplify_batch_v2(
                    llm_gen, a_validated, state,
                    source_dissection=pack.dissection, never_replace=True,
                )
                for post in a_amplified:
                    paragraphs = post.text.strip().split("\n\n")
                    post.original_opening = paragraphs[0] if paragraphs else ""
                    post.final_opening = post.original_opening
                    post.mechanic = "mirrored"
                    post.rating = 0
                    logger.info("[batch] %s: Batch A — %d variants generated (opener kept)",
                                post.label, getattr(post, 'versions_considered', 0))
                    self._emit(f"pack_{pack_num}", "post_ready", {
                        "label": post.label,
                        "batch": post.batch,
                        "mode": post.mode,
                        "text": post.text,
                        "word_count": post.word_count,
                        "mechanic": post.mechanic,
                        "final_opening": post.final_opening,
                        "entry_door": post.entry_door,
                        "voice_score": getattr(post, "voice_score", 0),
                        "source_number": pack_num,
                        "opener_variants": getattr(post, "opener_variants", []),
                        "versions_considered": getattr(post, "versions_considered", 0),
                    })
                a_validated = a_amplified

            # Phase B: batch amplify all B posts in one call
            self._check_cancel()
            if b_validated:
                b_amplified = amplify_batch_v2(llm_gen, b_validated, state)
            else:
                b_amplified = []

            # Merge back in original order, run saturation, emit post_ready for B posts
            b_map = {p.label: p for p in b_amplified}
            for post in validated_posts:
                if post.batch == "A":
                    matched = post
                else:
                    matched = b_map.get(post.label, post)
                sat = check_saturation(matched.text, published_corpus, n=6, threshold=5)
                matched.saturation_warning = sat
                if sat.get("warning"):
                    logger.warning(
                        "[batch] %s saturation WARN: %d shared 6-grams with %s",
                        matched.label, sat["count"], sat["worst_match_id"],
                    )
                amplified_posts.append(matched)
                state.arguments_compressed.append(matched.argument_compressed)
                if matched.batch == "B":
                    self._emit(f"pack_{pack_num}", "post_ready", {
                        "label": matched.label,
                        "batch": matched.batch,
                        "mode": matched.mode,
                        "text": matched.text,
                        "word_count": matched.word_count,
                        "mechanic": matched.mechanic,
                        "final_opening": getattr(matched, "final_opening", ""),
                        "entry_door": matched.entry_door,
                        "voice_score": getattr(matched, "voice_score", 0),
                        "source_number": pack_num,
                    })

            # Staged convergence testing (Haiku — classification)
            self._check_cancel()
            a_posts = [p for p in amplified_posts if p.batch == "A"]
            b_posts = [p for p in amplified_posts if p.batch == "B"]

            # In lean mode, skip the separate A-batch convergence test (saves 1 call)
            if a_posts and b_posts and not state.lean_mode:
                conv_a = convergence_test(llm_prep, a_posts, source[:200], state)
                pack.convergence_test_a = conv_a
                tracer.trace_decision(
                    f"pack_{pack_num}_convergence_a",
                    f"batch_a={'PASS' if conv_a.get('passed', True) else 'FAIL'}",
                    metadata={"posts": len(a_posts), "recommendation": conv_a.get("recommendation", "")},
                )

            conv = convergence_test(llm_prep, amplified_posts, source[:200], state)

            if not conv.get("passed", True):
                overlapping = conv.get("overlapping_posts", [])
                if not overlapping:
                    overlapping = [p.label for p in amplified_posts[1:3] if p.batch == "A"]
                recommendation = conv.get("recommendation", "")
                # Prefer the explicit replacement_angles list; fall back to parsing
                # the recommendation text if the LLM didn't produce a structured list.
                explicit_angles = conv.get("replacement_angles") or []
                if isinstance(explicit_angles, list):
                    angles = [str(a).strip() for a in explicit_angles if str(a).strip()]
                else:
                    angles = []
                if not angles:
                    angles = _split_recommendation_into_angles(recommendation)
                logger.info("[batch] Convergence FAIL — regenerating %s with %d distinct angle(s)",
                            overlapping, len(angles))
                pack.convergence_retry_attempted = True

                overlapping_kept_arguments = [
                    p.argument_compressed for p in amplified_posts
                    if p.label not in overlapping and p.argument_compressed
                ]
                kept_args_str = "\n".join(f"- {a}" for a in overlapping_kept_arguments[:6]) or "(none)"

                overlap_idx = 0
                for idx, post in enumerate(amplified_posts):
                    if post.label not in overlapping:
                        continue
                    assigned_angle = angles[overlap_idx % len(angles)] if angles else recommendation
                    overlap_idx += 1
                    diversity_note = (
                        f"CONVERGENCE REGEN: Your previous version argued: \"{post.argument_compressed}\". "
                        f"Other posts already argue:\n{kept_args_str}\n\n"
                        f"REQUIRED DIFFERENT ANGLE: {assigned_angle}\n\n"
                        "Do NOT argue any variant of the theses above. "
                        "Recommendation: " + (recommendation or "(none)")
                    )
                    from .pack_generator import transpose
                    regen_mode = "A" if post.batch == "A" else "B"
                    regen_doors = [post.entry_door] if post.batch == "B" and post.entry_door else None
                    regen_posts = transpose(
                        llm_gen, source, pack.dissection, mode=regen_mode, state=state,
                        doors=regen_doors, prior_arguments=overlapping_kept_arguments,
                        post_count=1, pack_number=pack_num, diversity_override=diversity_note,
                    )
                    new_post = regen_posts[0] if regen_posts else post
                    new_post = _enforce_word_count(new_post, state, llm=llm_gen)
                    new_post = amplify_post_v2(
                        llm_gen, new_post, state,
                        source_dissection=pack.dissection if new_post.batch == "A" else None,
                    )
                    amplified_posts[idx] = new_post
                    self._emit(f"pack_{pack_num}", "post_updated", {
                        "label": new_post.label,
                        "batch": new_post.batch,
                        "mode": new_post.mode,
                        "text": new_post.text,
                        "word_count": new_post.word_count,
                        "mechanic": new_post.mechanic,
                        "final_opening": getattr(new_post, "final_opening", ""),
                        "entry_door": new_post.entry_door,
                        "voice_score": getattr(new_post, "voice_score", 0),
                        "source_number": pack_num,
                        "reason": "convergence_regen",
                    })

                conv = convergence_test(llm_prep, amplified_posts, source[:200], state)
                tracer.trace_decision(
                    f"pack_{pack_num}_convergence_retry",
                    f"retry={'PASS' if conv.get('passed', True) else 'STILL_FAIL'}",
                    metadata=conv,
                )

                if not conv.get("passed", True):
                    pack.convergence_warning = True
                    logger.warning(
                        "[batch] Pack %d: convergence STILL_FAIL after regen — shipping with convergence_warning=True. Recommendation: %s",
                        pack_num, conv.get("recommendation", ""),
                    )

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
        """Use web search to find trending topics and facts about the founder and their domain."""
        if getattr(state, "llm_router", None):
            llm = state.llm_router.for_task("web_search")
        if not hasattr(llm, 'generate_with_search'):
            return {"searches": [], "trending_topics": [], "facts": []}

        beliefs = state.founder_ctx.get("beliefs", [])[:5]
        domains = [b.get("topic", "") for b in beliefs if b.get("topic")]

        founder_name = state.founder_slug.replace("_", " ").title()
        company_name = ""
        card_first = (state.personality_card or "").split("\n")[0]
        import re as _re
        company_match = _re.search(r'(?:of|at|founded|leads?|CEO of|co-?founder of)\s+([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*)', card_first)
        if company_match:
            company_name = company_match.group(1)

        domain_str = ", ".join(domains[:3]) if domains else "technology, startups"
        founder_line = f"{founder_name}"
        if company_name:
            founder_line += f" (founder/CEO of {company_name})"

        prompt = f"""You are researching current facts and news for {founder_line}, a thought leader who writes about: {domain_str}

Search the web for:
1. Recent news about {founder_name}{f' and {company_name}' if company_name else ''} — funding rounds, product launches, interviews, podcasts, public statements
2. Recent statistics, data points, or industry developments in: {domain_str}
3. Contrarian viewpoints or emerging trends the founder could reference

After searching, summarize your findings as JSON:
```json
{{
  "trending_topics": ["topic1", "topic2", ...],
  "facts": [
    {{"fact": "...", "source": "...", "relevance": "..."}},
    ...
  ],
  "contrarian_angles": ["angle1", "angle2", ...],
  "founder_news": [
    {{"headline": "...", "source": "...", "date": "..."}}
  ]
}}
```"""

        import time as _t
        _start = _t.time()
        result = llm.generate_with_search(
            prompt,
            system_prompt="You are a research assistant. Search the web and provide factual, current information.",
            temperature=0.3,
            max_tokens=2000,
            max_searches=5,
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
