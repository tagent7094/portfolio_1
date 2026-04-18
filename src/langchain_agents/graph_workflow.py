"""LangGraph workflow for the multi-agent content generation pipeline.

10-node pipeline:
  match_topic → generate_all_posts → audience_vote (→ regenerate?)
    → select_top → refine_posts → select_final
    → opening_line_massacre → humanize → quality_gate → track_coverage
"""

from __future__ import annotations

import json
import logging
from statistics import mean
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END

from ..config.founders import get_active_founder, get_viral_graph_path
from ..generation.audience_panel import load_audience_agents, score_posts_with_audience, select_top_posts
from ..generation.creativity import creativity_to_temperature
from ..generation.narrative_engines import NARRATIVE_ENGINES, generate_with_engine
from ..generation.opening_line_massacre import (
    apply_winning_opening,
    generate_opening_lines,
    score_opening_lines_with_audience,
)
from ..generation.refiner import refine_post_with_feedback
from ..graph.query import get_beliefs_for_topic, get_full_context, get_merged_context, get_personality_card, get_style_rules_for_platform, get_vocabulary_rules
from ..graph.store import load_graph
from ..humanization.quality_gate import quality_gate
from ..tracking.node_usage import track_node_usage
from .chains import match_topic_chain
from ..humanization.humanizer import humanize_post
from .llm_adapter import create_langchain_llm

logger = logging.getLogger(__name__)


class GenerationState(TypedDict):
    """State for the 10-node generation pipeline."""

    # Inputs
    topic: str
    platform: str
    transcript: str
    mode: str
    graph_path: str
    founder_slug: str
    viral_graph_path: str
    creativity: float  # 0.0-1.0
    num_variants: int  # how many to generate

    # Stage 1: Topic match + multi-generation
    topic_match: dict
    narrative: dict
    all_posts: list[dict]

    # Stage 2: Audience voting
    audience_votes: dict
    aggregated_scores: dict
    top_post_ids: list[str]
    generation_attempts: int  # for regeneration cycle

    # Stage 3: Refinement
    refined_posts: list[dict]

    # Stage 4: Opening Line Massacre
    opening_lines: list[dict]
    opening_votes: dict
    winning_opening: dict

    # Stage 5: Humanization + quality
    winning_post: dict
    humanized_post: str
    quality_result: dict
    humanize_attempts: int

    # Coverage tracking
    coverage_result: dict

    # Tracing
    agent_log: list[dict]
    _event_bus: Any


def _load_founder_graph(state: GenerationState):
    gp = state.get("graph_path", "")
    if not gp:
        from pathlib import Path
        gp = str(Path(__file__).parent.parent.parent / "data" / "knowledge-graph" / "graph.json")
    return load_graph(gp)


def _load_viral_graph(state: GenerationState):
    vgp = state.get("viral_graph_path", "")
    if not vgp:
        vgp = get_viral_graph_path()
    from pathlib import Path
    if Path(vgp).exists():
        return load_graph(vgp)
    return None


def _emit(state, stage, status, data=None, progress=0.0, agent_id=""):
    bus = state.get("_event_bus")
    if bus:
        from ..generation.pipeline_events import PipelineEvent
        bus.emit(PipelineEvent(stage=stage, status=status, data=data or {}, progress=progress, agent_id=agent_id))


def _log_graph_exploration(graph_name: str, action: str, query: str, results: list | dict, count: int = 0):
    """Rich terminal logging for graph exploration — shows what agents are finding."""
    import sys
    c = count if count else (len(results) if isinstance(results, list) else 1)
    print(f"\033[36m[{graph_name}]\033[0m \033[33m{action}\033[0m query=\"{query}\" → \033[32m{c} results\033[0m", file=sys.stderr)
    if isinstance(results, list):
        for r in results[:5]:
            if isinstance(r, dict):
                label = r.get('label', r.get('name', r.get('title', r.get('stance', r.get('id', '?')))))
                ntype = r.get('node_type', r.get('type', ''))
                score = r.get('confidence', r.get('engagement', r.get('mean', '')))
                extra = f" (score={score})" if score else ""
                print(f"  \033[2m  → [{ntype}] {str(label)[:80]}{extra}\033[0m", file=sys.stderr)
        if len(results) > 5:
            print(f"  \033[2m  ... and {len(results) - 5} more\033[0m", file=sys.stderr)


# ── Node 1: Match Topic ──

def match_topic_node(state: GenerationState) -> dict:
    import sys
    logger.info("Stage 1a: Matching topic to graph...")
    _emit(state, "match_topic", "started")
    print(f"\n{'='*70}\n\033[1m[STAGE 1] TOPIC MATCHING\033[0m\n{'='*70}", file=sys.stderr)

    graph = _load_founder_graph(state)
    llm = create_langchain_llm()
    topic = state["topic"]

    print(f"\033[1mTopic:\033[0m \"{topic}\"", file=sys.stderr)
    print(f"\033[1mFounder graph:\033[0m {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges", file=sys.stderr)

    beliefs = get_beliefs_for_topic(graph, topic)
    _log_graph_exploration("FounderGraph", "get_beliefs_for_topic", topic, beliefs)

    stories = [d for _, d in graph.nodes(data=True) if d.get("node_type") == "story"][:10]
    _log_graph_exploration("FounderGraph", "get_stories", "all", stories)

    models = [d for _, d in graph.nodes(data=True) if d.get("node_type") == "thinking_model"][:5]
    _log_graph_exploration("FounderGraph", "get_thinking_models", "all", models)

    beliefs_text = "\n".join(f"- [{b.get('id', '?')}] {b.get('topic', '?')}: {b.get('stance', '?')}" for b in beliefs[:15]) or "None."
    stories_text = "\n".join(f"- [{s.get('id', '?')}] {s.get('title', '?')}: {s.get('summary', '?')}" for s in stories) or "None."
    models_text = "\n".join(f"- {m.get('name', '?')}: {m.get('description', '?')}" for m in models) or "None."

    match = match_topic_chain(llm, topic, beliefs_text, stories_text, models_text)
    print(f"\033[32m[TopicMatch] Suggested angle:\033[0m {match.get('suggested_angle', 'N/A')}", file=sys.stderr)

    narrative = {
        "id": "topic_match",
        "narrative": match.get("suggested_angle", topic),
        "angle": f"Based on founder's beliefs about {topic}",
        "hook": match.get("suggested_angle", topic)[:100],
    }

    _emit(state, "match_topic", "completed", {"angle": match.get("suggested_angle", "")})
    return {"topic_match": match, "narrative": narrative, "agent_log": [{"step": "topic_match", "match": match}]}


# ── Node 2: Generate All Posts (10 engines, dual-graph) ──

def generate_all_posts_node(state: GenerationState) -> dict:
    import sys
    
    num_variants = state.get("num_variants", 10)
    engines_to_run = NARRATIVE_ENGINES[:num_variants]

    logger.info("Stage 1b: Generating %d post variants...", len(engines_to_run))
    _emit(state, "generate_all_posts", "started", {"total_engines": len(engines_to_run)})

    print(f"\n{'='*70}\n\033[1m[STAGE 2] MULTI-ENGINE GENERATION\033[0m\n{'='*70}", file=sys.stderr)

    graph = _load_founder_graph(state)
    viral_graph = _load_viral_graph(state)
    creativity = state.get("creativity", 0.5)

    print(f"\033[1mCreativity:\033[0m {creativity:.0%}", file=sys.stderr)
    print(f"\033[1mFounder graph:\033[0m {graph.number_of_nodes()} nodes", file=sys.stderr)
    if viral_graph:
        print(f"\033[1mViral graph:\033[0m {viral_graph.number_of_nodes()} nodes", file=sys.stderr)
    else:
        print(f"\033[33m[ViralGraph] Not loaded (run viral ingestion first)\033[0m", file=sys.stderr)

    # Use native LLMProvider for streaming
    from ..llm.factory import create_llm
    llm = create_llm()

    narrative = state["narrative"]
    platform = state["platform"]
    topic = state["topic"]

    # Merged context (founder + viral)
    context = get_merged_context(graph, viral_graph, topic, platform, creativity)

    # Log what was found in graphs
    _log_graph_exploration("FounderGraph", "get_beliefs_for_topic", topic, context.get("beliefs", []))
    _log_graph_exploration("FounderGraph", "get_stories_for_beliefs", topic, context.get("stories", []))
    _log_graph_exploration("FounderGraph", "get_style_rules", platform, context.get("style_rules", []))

    viral_ctx = context.get("viral_context", {})
    if viral_ctx:
        _log_graph_exploration("ViralGraph", "get_hooks", topic, viral_ctx.get("hooks", []))
        _log_graph_exploration("ViralGraph", "get_patterns", topic, viral_ctx.get("patterns", []))
        _log_graph_exploration("ViralGraph", "get_techniques", topic, viral_ctx.get("techniques", []))

    print(f"\033[1mPersonality card:\033[0m {len(context.get('personality_card', ''))} chars", file=sys.stderr)
    print(f"\033[1mViral context block:\033[0m {len(context.get('viral_context_block', ''))} chars", file=sys.stderr)
    print(f"\033[1mGenerating with {len(engines_to_run)} engines...\033[0m", file=sys.stderr)

    posts = []
    log_entries = []

    for i, engine in enumerate(engines_to_run):
        logger.info("  Engine %d/%d: %s", i + 1, len(engines_to_run), engine["name"])
        _emit(state, "generate_all_posts", "generating", {
            "engine_id": engine["id"], "engine_name": engine["name"], "post_index": i,
        })

        def make_token_cb(eng_id, idx):
            buf = []
            def cb(token):
                buf.append(token)
                if len(buf) >= 5 or "\n" in token:
                    _emit(state, "llm_token", "token", {"engine_id": eng_id, "post_index": idx, "token": "".join(buf)})
                    buf.clear()
            return cb, buf

        token_cb, token_buf = make_token_cb(engine["id"], i)

        try:
            post = generate_with_engine(engine, narrative, platform, context, llm, token_callback=token_cb)
            if token_buf:
                _emit(state, "llm_token", "token", {"engine_id": engine["id"], "post_index": i, "token": "".join(token_buf)})
                token_buf.clear()
            posts.append(post)
            log_entries.append({"step": "generate_post", "engine": engine["name"], "length": len(post["text"])})
        except Exception as e:
            logger.error("  Engine %s failed: %s", engine["id"], e)
            log_entries.append({"step": "generate_post", "engine": engine["name"], "error": str(e)})

        _emit(state, "generate_all_posts", "progress", {
            "engine_id": engine["id"], "engine_name": engine["name"], "post_index": i,
            "post": posts[-1] if posts and posts[-1]["engine_id"] == engine["id"] else None,
        }, progress=(i + 1) / len(engines_to_run))

    _emit(state, "generate_all_posts", "completed", {"count": len(posts)})
    attempts = state.get("generation_attempts", 0) + 1
    return {"all_posts": posts, "generation_attempts": attempts, "agent_log": state.get("agent_log", []) + log_entries}


# ── Node 3: Audience Vote ──

def audience_vote_node(state: GenerationState) -> dict:
    import sys
    logger.info("Stage 2: Audience voting on %d posts...", len(state.get("all_posts", [])))
    _emit(state, "audience_vote", "started")

    posts = state.get("all_posts", [])
    print(f"\n{'='*70}\n\033[1m[STAGE 3] AUDIENCE VOTING\033[0m\n{'='*70}", file=sys.stderr)
    print(f"\033[1mPosts to vote on:\033[0m {len(posts)}", file=sys.stderr)
    for p in posts:
        print(f"  \033[2m→ [{p.get('engine_name', '?')}] {p.get('text', '')[:60]}...\033[0m", file=sys.stderr)

    llm = create_langchain_llm()
    graph = _load_founder_graph(state)
    personality_card = get_personality_card(graph)
    audience_agents = load_audience_agents()
    print(f"\033[1mAudience agents:\033[0m {', '.join(a['name'] for a in audience_agents)}", file=sys.stderr)

    if not audience_agents:
        return {"audience_votes": {}, "aggregated_scores": {}, "top_post_ids": [p["id"] for p in posts[:3]], "agent_log": state.get("agent_log", [])}

    def event_cb(agent_id, agent_name, votes):
        _emit(state, "audience_vote", "progress", {"agent_id": agent_id, "agent_name": agent_name, "votes": votes}, agent_id=agent_id)

    result = score_posts_with_audience(llm, posts, audience_agents, personality_card, event_callback=event_cb)

    _emit(state, "audience_vote", "completed", {"aggregated": result["aggregated"], "top_ids": result["top_ids"]})
    return {
        "audience_votes": result["agent_votes"],
        "aggregated_scores": result["aggregated"],
        "top_post_ids": result["top_ids"],
        "agent_log": state.get("agent_log", []) + [{"step": "audience_vote", "top_ids": result["top_ids"]}],
    }


# ── Conditional: should we regenerate? ──

def should_regenerate(state: GenerationState) -> str:
    aggregated = state.get("aggregated_scores", {})
    if not aggregated:
        return "proceed"
    max_score = max((v.get("mean", 0) for v in aggregated.values()), default=0)
    attempts = state.get("generation_attempts", 1)
    if max_score < 6.0 and attempts < 2:
        logger.info("  Max score %.1f < 6.0, regenerating (attempt %d)...", max_score, attempts + 1)
        _emit(state, "audience_vote", "regenerating", {"max_score": max_score, "attempt": attempts})
        return "regenerate"
    return "proceed"


# ── Node 4: Select Top ──

def select_top_node(state: GenerationState) -> dict:
    logger.info("Stage 2b: Selecting top posts...")
    top_ids = state.get("top_post_ids", [])
    if not top_ids:
        top_ids = select_top_posts(state.get("aggregated_scores", {}), n=3)
    _emit(state, "select_top", "completed", {"top_ids": top_ids})
    return {"top_post_ids": top_ids}


# ── Node 5: Refine Posts ──

def refine_posts_node(state: GenerationState) -> dict:
    logger.info("Stage 3: Refining top posts...")
    _emit(state, "refine_posts", "started")

    llm = create_langchain_llm()
    graph = _load_founder_graph(state)
    personality_card = get_personality_card(graph)
    platform = state["platform"]
    all_posts = state.get("all_posts", [])
    top_ids = state.get("top_post_ids", [])
    audience_votes = state.get("audience_votes", {})
    audience_agents = load_audience_agents()

    refined = []
    for i, pid in enumerate(top_ids):
        post = next((p for p in all_posts if p["id"] == pid), None)
        if not post:
            continue
        feedback = {}
        for agent in audience_agents:
            aid = agent["id"]
            if aid in audience_votes and pid in audience_votes[aid]:
                feedback[agent["name"]] = audience_votes[aid][pid]

        result = refine_post_with_feedback(llm, post, feedback, personality_card, platform)
        refined.append(result)
        _emit(state, "refine_posts", "progress", {
            "post_id": pid, "original_text": post["text"][:200], "refined_text": result["refined_text"][:200],
            "engine_name": post.get("engine_name", ""), "index": i,
        }, progress=(i + 1) / len(top_ids))

    _emit(state, "refine_posts", "completed", {"count": len(refined)})
    return {"refined_posts": refined, "agent_log": state.get("agent_log", []) + [{"step": "refine", "count": len(refined)}]}


# ── Node 6: Select Final ──

def select_final_node(state: GenerationState) -> dict:
    logger.info("Stage 3b: Selecting final post...")
    refined = state.get("refined_posts", [])
    aggregated = state.get("aggregated_scores", {})

    if not refined:
        all_posts = state.get("all_posts", [])
        winner = all_posts[0] if all_posts else {"id": "fallback", "text": "No posts generated."}
        return {"winning_post": winner}

    best = refined[0]
    best_score = 0
    for r in refined:
        score = aggregated.get(r["id"], {}).get("mean", 0)
        if score > best_score:
            best_score = score
            best = r

    winner = {
        "id": best["id"], "text": best["refined_text"],
        "original_text": best["original_text"],
        "engine_id": best.get("engine_id", ""), "engine_name": best.get("engine_name", ""),
    }
    _emit(state, "select_final", "completed", {"winner_id": winner["id"], "score": best_score})
    return {"winning_post": winner}


# ── Node 7: Opening Line Massacre ──

def opening_line_massacre_node(state: GenerationState) -> dict:
    logger.info("Stage 4: Opening Line Massacre...")
    _emit(state, "opening_massacre", "started")

    from ..llm.factory import create_llm
    llm = create_llm()
    graph = _load_founder_graph(state)
    viral_graph = _load_viral_graph(state)
    creativity = state.get("creativity", 0.5)

    post = state["winning_post"]
    context = get_full_context(graph, state["topic"], state["platform"])

    viral_context = None
    if viral_graph and viral_graph.number_of_nodes() > 0:
        from ..graph.viral_query import get_viral_context_for_topic
        viral_context = get_viral_context_for_topic(viral_graph, state["topic"], creativity)

    # Generate 10 openings
    openings = generate_opening_lines(post["text"], context, viral_context, llm, n=10, platform=state.get("platform", "linkedin"))
    _emit(state, "opening_massacre", "generating", {"count": len(openings), "openings": [{"id": o["id"], "text": o["text"], "strategy": o.get("strategy", "")} for o in openings]})

    # Audience vote on openings
    audience_agents = load_audience_agents()
    post_body = "\n\n".join(post["text"].strip().split("\n\n")[1:])

    def event_cb(agent_id, agent_name, votes):
        _emit(state, "opening_massacre", "voting", {"agent_id": agent_id, "agent_name": agent_name, "votes": votes})

    vote_result = score_opening_lines_with_audience(
        llm, openings, post_body, audience_agents,
        context.get("personality_card", ""), event_callback=event_cb,
    )

    winning = vote_result["winning_line"]
    updated_text = apply_winning_opening(post["text"], winning)

    _emit(state, "opening_massacre", "completed", {
        "winning_id": vote_result["winning_id"],
        "winning_text": winning["text"],
        "aggregated": vote_result["aggregated"],
    })

    updated_post = {**post, "text": updated_text, "winning_opening": winning}

    return {
        "winning_post": updated_post,
        "opening_lines": openings,
        "opening_votes": vote_result["agent_votes"],
        "winning_opening": winning,
        "agent_log": state.get("agent_log", []) + [{"step": "opening_massacre", "winner": winning["text"]}],
    }


# ── Node 8: Humanize ──

def humanize_node(state: GenerationState) -> dict:
    logger.info("Stage 5: Humanizing...")
    _emit(state, "humanize", "started")

    graph = _load_founder_graph(state)
    # humanize_post requires an LLMProvider (not a langchain LLM)
    from ..llm.factory import create_llm
    llm = create_llm(purpose="generation")
    platform = state["platform"]

    post_text = state["winning_post"]["text"]
    personality_card = state.get("personality_card", "")
    humanized = humanize_post(
        post_text, graph, llm,
        platform=platform,
        personality_card=personality_card,
    )["humanized"]

    attempts = state.get("humanize_attempts", 0) + 1
    _emit(state, "humanize", "completed", {"length": len(humanized), "attempt": attempts})
    return {
        "humanized_post": humanized, "humanize_attempts": attempts,
        "agent_log": state.get("agent_log", []) + [{"step": "humanize", "attempt": attempts}],
    }


# ── Node 9: Quality Gate ──

def quality_gate_node(state: GenerationState) -> dict:
    logger.info("Stage 5b: Quality gate...")
    graph = _load_founder_graph(state)
    result = quality_gate(state["humanized_post"], graph)
    _emit(state, "quality_gate", "completed", {"score": result["score"], "passed": result["passed"], "checks": result["checks"]})
    logger.info("  Quality: %d%% (%s)", result["score"], "PASS" if result["passed"] else "FAIL")
    return {"quality_result": result, "agent_log": state.get("agent_log", []) + [{"step": "quality_gate", "score": result["score"]}]}


# ── Node 10: Track Coverage ──

def track_coverage_node(state: GenerationState) -> dict:
    logger.info("Stage 6: Tracking node coverage...")
    graph = _load_founder_graph(state)
    founder_slug = state.get("founder_slug", "sharath")
    result = track_node_usage(
        state.get("humanized_post", ""), graph,
        state["topic"], state["platform"], founder_slug,
    )
    _emit(state, "track_coverage", "completed", {"matched_count": len(result.get("matched_nodes", []))})
    return {"coverage_result": result}


# ── Conditional: rehumanize? ──

def should_rehumanize(state: GenerationState) -> str:
    qr = state.get("quality_result", {})
    attempts = state.get("humanize_attempts", 0)
    if not qr.get("passed", True) and attempts < 3:
        return "rehumanize"
    return "done"


# ── Build the workflow ──

def build_generation_workflow() -> StateGraph:
    workflow = StateGraph(GenerationState)

    workflow.add_node("match_topic", match_topic_node)
    workflow.add_node("generate_all_posts", generate_all_posts_node)
    workflow.add_node("audience_vote", audience_vote_node)
    workflow.add_node("select_top", select_top_node)
    workflow.add_node("refine_posts", refine_posts_node)
    workflow.add_node("select_final", select_final_node)
    workflow.add_node("opening_line_massacre", opening_line_massacre_node)
    workflow.add_node("humanize", humanize_node)
    workflow.add_node("quality_gate", quality_gate_node)
    workflow.add_node("track_coverage", track_coverage_node)

    workflow.set_entry_point("match_topic")
    workflow.add_edge("match_topic", "generate_all_posts")
    workflow.add_edge("generate_all_posts", "audience_vote")

    # Conditional: regenerate if scores too low
    workflow.add_conditional_edges(
        "audience_vote",
        should_regenerate,
        {"regenerate": "generate_all_posts", "proceed": "select_top"},
    )

    workflow.add_edge("select_top", "refine_posts")
    workflow.add_edge("refine_posts", "select_final")
    workflow.add_edge("select_final", "opening_line_massacre")
    workflow.add_edge("opening_line_massacre", "humanize")
    workflow.add_edge("humanize", "quality_gate")

    # Conditional: rehumanize or finish
    workflow.add_conditional_edges(
        "quality_gate",
        should_rehumanize,
        {"rehumanize": "humanize", "done": "track_coverage"},
    )

    workflow.add_edge("track_coverage", END)

    return workflow.compile()


# ── Entry points ──

def run_topic_generation(topic: str, platform: str = "linkedin", graph_path: str = "", founder_slug: str = "sharath", num_variants: int = 10) -> GenerationState:
    from pathlib import Path
    if not graph_path:
        try:
            config = get_active_founder()
            graph_path = config["graph_path"]
            founder_slug = config["slug"]
        except Exception:
            graph_path = str(Path(__file__).parent.parent.parent / "data" / "knowledge-graph" / "graph.json")

    workflow = build_generation_workflow()
    initial_state = _make_initial_state(topic, platform, graph_path, founder_slug, creativity=0.5, num_variants=num_variants)
    return workflow.invoke(initial_state)


def run_topic_generation_with_events(topic, platform, graph_path, event_bus, founder_slug="sharath", creativity=0.5, num_variants: int = 10) -> dict:
    from pathlib import Path
    if not graph_path:
        try:
            config = get_active_founder()
            graph_path = config["graph_path"]
            founder_slug = config["slug"]
        except Exception:
            graph_path = str(Path(__file__).parent.parent.parent / "data" / "knowledge-graph" / "graph.json")

    workflow = build_generation_workflow()
    initial_state = _make_initial_state(topic, platform, graph_path, founder_slug, creativity, event_bus, num_variants=num_variants)
    result = workflow.invoke(initial_state)

    # Strip non-serializable fields
    return {k: v for k, v in result.items() if not k.startswith("_")}


def _make_initial_state(topic, platform, graph_path, founder_slug, creativity=0.5, event_bus=None, num_variants=10):
    return {
        "topic": topic,
        "platform": platform,
        "transcript": "",
        "mode": "topic",
        "graph_path": graph_path,
        "founder_slug": founder_slug,
        "viral_graph_path": get_viral_graph_path(),
        "creativity": creativity,
        "num_variants": num_variants,
        "topic_match": {},
        "narrative": {},
        "all_posts": [],
        "audience_votes": {},
        "aggregated_scores": {},
        "top_post_ids": [],
        "generation_attempts": 0,
        "refined_posts": [],
        "opening_lines": [],
        "opening_votes": {},
        "winning_opening": {},
        "winning_post": {},
        "humanized_post": "",
        "quality_result": {},
        "humanize_attempts": 0,
        "coverage_result": {},
        "agent_log": [],
        "_event_bus": event_bus,
    }
