"""LangGraph workflow for Viral Post Adaptation Framework v2.

7-node pipeline:
  internalize_founder → dissect_source → generate_adaptations (x5 seq)
    → audience_vote → refine_posts → v2_quality_filter → track_coverage
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, TypedDict

from ..config.founders import get_viral_graph_path
from ..customizer.founder_loader import load_raw_founder_data
from ..generation.audience_panel import load_audience_agents, score_posts_with_audience
from ..generation.creativity import creativity_to_temperature
from ..generation.pipeline_events import PipelineEvent
from ..generation.refiner import refine_post_with_feedback
from ..graph.query import get_deep_founder_context, get_personality_card
from ..graph.store import load_graph
from ..graph.viral_query import get_viral_context_for_topic, format_viral_context_for_prompt
from ..humanization.quality_gate import quality_gate
from ..llm.factory import create_llm
from ..tracking.node_usage import track_node_usage

logger = logging.getLogger(__name__)

# ── Prompt loading ──

PROMPTS_DIR = Path(__file__).parent.parent / "customizer" / "prompts"


def _load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8")


# ── Variant blueprints (different entry doors per the framework) ──

VARIANT_BLUEPRINTS = [
    {
        "number": 1,
        "register": "combative",
        "instruction": "Sharp contrarian opening. The founder disagrees with something everyone accepts. "
                       "Use a tension/collision from the founder's world. Combative but earned."
    },
    {
        "number": 2,
        "register": "reflective",
        "instruction": "Micro-story opening. Drop into a specific scene — a physical moment with sensory "
                       "detail. The insight emerges from the scene, not before it."
    },
    {
        "number": 3,
        "register": "data-heavy",
        "instruction": "Unexpected number or fact as the door in. The number creates a gap the reader "
                       "wants closed. Build to insight through evidence, not opinion."
    },
    {
        "number": 4,
        "register": "confession",
        "instruction": "Earned authority through admission. The founder confesses something — a mistake, "
                       "a fear, a doubt. Vulnerability as the door. The insight is earned, not declared."
    },
    {
        "number": 5,
        "register": "macro",
        "instruction": "Broader cross-industry pattern. The founder sees something in their world that "
                       "maps to a universal truth. Macro lens — anyone in any industry feels this."
    },
]


# ── State ──

class AdaptationV2State(TypedDict):
    # Inputs
    source_post: str
    platform: str
    founder_slug: str
    creativity: float
    num_variants: int
    graph_path: str
    viral_graph_path: str

    # Step 1 output
    founder_internalization: dict

    # Step 2 output
    source_dissection: dict

    # Generation
    adaptations: list  # list of variant dicts
    events_used: list  # flat list of all events used

    # Reused pipeline stages
    audience_votes: dict
    aggregated_scores: dict
    top_post_ids: list
    refined_posts: list
    quality_results: list

    # Coverage
    coverage_result: dict
    traceability: dict

    # Internal
    agent_log: list
    _event_bus: Any
    _llm: Any
    _founder_ctx: dict
    _viral_ctx: dict


def _emit(state, stage, status, data=None, progress=0.0):
    bus = state.get("_event_bus")
    if bus:
        bus.emit(PipelineEvent(stage=stage, status=status, data=data or {}, progress=progress))


def _parse_json(text: str) -> dict:
    """Extract JSON from LLM response that may contain markdown fences."""
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try extracting from code fences
    m = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Try finding first { ... }
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def _format_beliefs(beliefs: list) -> str:
    return "\n".join(
        f"- [{b.get('node_id', '?')}] {b.get('topic', '?')}: {b.get('stance', '?')}"
        for b in beliefs[:15]
    ) or "None available."


def _format_stories(stories: list) -> str:
    return "\n".join(
        f"- [{s.get('node_id', '?')}] {s.get('title', '?')}: {s.get('summary', '')[:120]}"
        for s in stories[:12]
    ) or "None available."


def _format_contrast_pairs(pairs: list) -> str:
    return "\n".join(
        f"- \"{c.get('left', '?')}\" vs \"{c.get('right', '?')}\" — {c.get('description', '')[:80]}"
        for c in pairs[:8]
    ) or "None available."


def _format_thinking_models(models: list) -> str:
    return "\n".join(
        f"- {m.get('name', '?')}: {m.get('description', '')[:100]}"
        for m in models[:8]
    ) or "None available."


def _format_style_rules(rules: list) -> str:
    return "\n".join(
        f"- [{r.get('rule_type', '?')}] {r.get('description', '')[:120]}"
        for r in rules[:12]
    ) or "None available."


# ── Node 1: Internalize Founder ──

def internalize_founder_node(state: AdaptationV2State) -> dict:
    print(f"\n{'='*70}\n\033[1m[V2 STEP 1] INTERNALIZE FOUNDER\033[0m\n{'='*70}", file=sys.stderr)
    _emit(state, "internalize_founder", "started")

    llm = create_llm(purpose="generation")
    founder_slug = state["founder_slug"]
    platform = state["platform"]

    # Load graph data (unfiltered)
    graph = load_graph(state["graph_path"])
    founder_ctx = get_deep_founder_context(graph, platform)

    # Load raw files
    raw_data = load_raw_founder_data(founder_slug)
    print(f"  Raw files: voice_dna={len(raw_data['raw_voice_dna'])}c, "
          f"story_bank={len(raw_data['raw_story_bank'])}c, "
          f"posts={len(raw_data['founder_posts_sample'])}c", file=sys.stderr)

    # Build prompt
    prompt_template = _load_prompt("internalize_founder")
    prompt = prompt_template.format(
        personality_card=founder_ctx.get("personality_card", "")[:3000],
        beliefs=_format_beliefs(founder_ctx["beliefs"]),
        stories=_format_stories(founder_ctx["stories"]),
        contrast_pairs=_format_contrast_pairs(founder_ctx["contrast_pairs"]),
        thinking_models=_format_thinking_models(founder_ctx["thinking_models"]),
        raw_voice_dna=raw_data["raw_voice_dna"][:6000],
        raw_story_bank=raw_data["raw_story_bank"][:6000],
        founder_posts_sample=raw_data["founder_posts_sample"][:4000],
    )

    # Retry on empty (free-tier models can return empty)
    result = ""
    for attempt in range(3):
        result = llm.generate(prompt, temperature=0.3, max_tokens=4000)
        if result and len(result.strip()) > 50:
            break
        print(f"  \033[33mEmpty internalization response (attempt {attempt+1}/3), retrying...\033[0m", file=sys.stderr)
        import time
        time.sleep(2)
    internalization = _parse_json(result)

    if not internalization:
        print("  \033[31mWARN: Failed to parse internalization JSON, using raw text\033[0m", file=sys.stderr)
        internalization = {"raw": result[:2000]}

    print(f"  Internalization: {len(internalization.get('tensions', []))} tensions, "
          f"{len(internalization.get('signature_scenes', []))} scenes, "
          f"word range: {internalization.get('word_count_range', 'unknown')}", file=sys.stderr)

    _emit(state, "internalize_founder", "completed", {
        "tensions_count": len(internalization.get("tensions", [])),
        "scenes_count": len(internalization.get("signature_scenes", [])),
        "word_count_range": internalization.get("word_count_range", []),
    })

    return {
        "founder_internalization": internalization,
        "_llm": llm,
        "_founder_ctx": founder_ctx,
        "traceability": founder_ctx.get("traceability", {}),
    }


# ── Node 2: Dissect Source Post ──

def dissect_source_node(state: AdaptationV2State) -> dict:
    print(f"\n{'='*70}\n\033[1m[V2 STEP 2] DISSECT SOURCE POST\033[0m\n{'='*70}", file=sys.stderr)
    _emit(state, "dissect_source", "started")

    llm = state.get("_llm") or create_llm(purpose="generation")

    prompt_template = _load_prompt("dissect_source")
    prompt = prompt_template.format(
        source_post=state["source_post"],
        platform=state["platform"],
    )

    # Retry on empty (free-tier models can return empty)
    result = ""
    for attempt in range(3):
        result = llm.generate(prompt, temperature=0.2, max_tokens=2000)
        if result and len(result.strip()) > 50:
            break
        print(f"  \033[33mEmpty dissection response (attempt {attempt+1}/3), retrying...\033[0m", file=sys.stderr)
        import time
        time.sleep(2)
    dissection = _parse_json(result)

    if not dissection:
        print("  \033[31mWARN: Failed to parse dissection JSON, using defaults\033[0m", file=sys.stderr)
        dissection = {"narrative_arc": "unknown", "hook_mechanics": [], "sentence_count": 0}

    hooks = dissection.get("hook_mechanics", [])
    print(f"  Arc: {dissection.get('narrative_arc', '?')}", file=sys.stderr)
    print(f"  Hook: {len(hooks)} sentences, ending: {dissection.get('ending_type', '?')}", file=sys.stderr)
    for h in hooks:
        print(f"    → [{h.get('structural_function', '?')}] {h.get('sentence', '?')[:60]}...", file=sys.stderr)

    _emit(state, "dissect_source", "completed", {
        "narrative_arc": dissection.get("narrative_arc", ""),
        "hook_count": len(hooks),
        "ending_type": dissection.get("ending_type", ""),
    })

    return {"source_dissection": dissection}


# ── Node 3: Generate Adaptations (x5 sequential) ──

def generate_adaptations_node(state: AdaptationV2State) -> dict:
    num = state.get("num_variants", 5)
    print(f"\n{'='*70}\n\033[1m[V2 STEP 3] GENERATE {num} ADAPTATIONS (sequential)\033[0m\n{'='*70}", file=sys.stderr)
    _emit(state, "generate_adaptations", "started", {"total": num})

    llm = state.get("_llm") or create_llm(purpose="generation")
    founder_ctx = state.get("_founder_ctx", {})
    internalization = state.get("founder_internalization", {})
    dissection = state.get("source_dissection", {})

    # Format context for prompts
    vocab = founder_ctx.get("vocabulary", {})
    hooks_text = json.dumps(dissection.get("hook_mechanics", []), indent=2)
    word_range = internalization.get("word_count_range", [150, 300])
    word_range_str = f"{word_range[0]}-{word_range[1]} words" if isinstance(word_range, list) and len(word_range) == 2 else str(word_range)

    # Viral context
    viral_block = ""
    vgp = state.get("viral_graph_path", "")
    if vgp and Path(vgp).exists():
        try:
            viral_graph = load_graph(vgp)
            if viral_graph.number_of_nodes() > 0:
                # Extract topic from source post (first line as proxy)
                topic_proxy = state["source_post"].split("\n")[0][:100]
                viral_ctx = get_viral_context_for_topic(viral_graph, topic_proxy, state.get("creativity", 0.5))
                viral_block = format_viral_context_for_prompt(viral_ctx, state.get("creativity", 0.5))
        except Exception as e:
            print(f"  \033[33mViral context failed: {e}\033[0m", file=sys.stderr)

    # Anti-patterns (reuse from existing)
    anti_patterns = (
        "BANNED WORDS: landscape, navigate, leverage, foster, facilitate, utilize, robust, "
        "comprehensive, paradigm, innovative, synergy, holistic, ecosystem, streamline, "
        "empower, endeavor, moreover, furthermore, henceforth, delve, multifaceted, "
        "game-changer, impactful\n"
        "BANNED PHRASES: 'Here\\'s what people miss', 'Hot take', 'Let me tell you', "
        "'In today\\'s world', 'Here\\'s the thing', 'I\\'ll be honest'\n"
        "BANNED STRUCTURES: Parallel triplets, rhetorical questions as hooks, "
        "numbered lists disguised as prose, 'I used to think X, now I think Y' as first line"
    )

    prompt_template = _load_prompt("adapt_viral_v2")
    adaptations = []
    all_events = []
    blueprints = VARIANT_BLUEPRINTS[:num]

    for i, bp in enumerate(blueprints):
        print(f"\n  \033[1mVariant {i+1}/{num}: {bp['register']}\033[0m", file=sys.stderr)
        _emit(state, "generate_adaptations", "progress", {
            "index": i, "register": bp["register"]
        }, progress=(i + 1) / num)

        events_text = "\n".join(f"- {e}" for e in all_events) or "None yet (this is the first variant)."

        prompt = prompt_template.format(
            platform=state["platform"],
            variant_number=bp["number"],
            variant_blueprint=bp["instruction"],
            founder_internalization=json.dumps(internalization, indent=2)[:4000],
            source_dissection=json.dumps(dissection, indent=2)[:2000],
            hook_mechanics=hooks_text,
            personality_card=founder_ctx.get("personality_card", "")[:2000],
            beliefs=_format_beliefs(founder_ctx.get("beliefs", [])),
            stories=_format_stories(founder_ctx.get("stories", [])),
            style_rules=_format_style_rules(founder_ctx.get("style_rules", [])),
            viral_context_block=viral_block[:1500] if viral_block else "No viral patterns available.",
            events_already_used=events_text,
            word_count_range=word_range_str,
            phrases_used=", ".join(vocab.get("phrases_used", [])[:8]) or "None specified.",
            phrases_never=", ".join(vocab.get("phrases_never", [])[:8]) or "None specified.",
            pronoun_rules=json.dumps(vocab.get("pronoun_rules", {})),
            punctuation_rules=", ".join(vocab.get("punctuation_rules", [])) if vocab.get("punctuation_rules") else "None specified.",
            anti_patterns=anti_patterns,
        )

        temperature = creativity_to_temperature(state.get("creativity", 0.5))

        # Retry up to 3 times on empty responses (common with free-tier models)
        result = ""
        for attempt in range(3):
            result = llm.generate(prompt, temperature=temperature, max_tokens=llm.max_output_tokens)
            if result and len(result.strip()) > 20:
                break
            print(f"    \033[33mEmpty/short response (attempt {attempt+1}/3), retrying...\033[0m", file=sys.stderr)
            import time
            time.sleep(2)

        # Extract planning block
        planning_match = re.search(r"<planning>(.*?)</planning>", result, re.DOTALL)
        planning = planning_match.group(1).strip() if planning_match else ""

        # Extract events used
        events_match = re.search(r"<events_used>(.*?)</events_used>", result, re.DOTALL)
        variant_events = []
        if events_match:
            for line in events_match.group(1).strip().split("\n"):
                line = line.strip().lstrip("- ")
                if line:
                    variant_events.append(line)
                    all_events.append(line)

        # Extract the post text (everything after the last XML block)
        post_text = result
        # Remove planning and events blocks
        post_text = re.sub(r"<planning>.*?</planning>", "", post_text, flags=re.DOTALL)
        post_text = re.sub(r"<events_used>.*?</events_used>", "", post_text, flags=re.DOTALL)
        post_text = post_text.strip()

        word_count = len(post_text.split())
        print(f"    → {word_count} words, {len(variant_events)} events used", file=sys.stderr)
        if planning:
            print(f"    Planning: {planning[:120]}...", file=sys.stderr)

        adaptations.append({
            "id": f"v2_{bp['register']}_{state['platform']}",
            "text": post_text,
            "engine_id": f"v2_{bp['register']}",
            "engine_name": f"V2 {bp['register'].title()}",
            "platform": state["platform"],
            "planning": planning,
            "events_used": variant_events,
            "word_count": word_count,
        })

    _emit(state, "generate_adaptations", "completed", {"count": len(adaptations)})

    return {"adaptations": adaptations, "events_used": all_events}


# ── Node 4: Audience Vote (reuse) ──

def audience_vote_node(state: AdaptationV2State) -> dict:
    print(f"\n{'='*70}\n\033[1m[V2 STEP 4] AUDIENCE VOTING\033[0m\n{'='*70}", file=sys.stderr)
    _emit(state, "audience_vote", "started")

    llm = state.get("_llm") or create_llm(purpose="generation")
    variants = state.get("adaptations", [])
    graph = load_graph(state["graph_path"])
    personality_card = get_personality_card(graph)
    audience_agents = load_audience_agents()

    def vote_cb(agent_id, agent_name, votes):
        _emit(state, "audience_vote", "progress", {
            "agent_id": agent_id, "agent_name": agent_name,
            "votes": {k: {"score": v.get("score", 5), "feedback": v.get("feedback", "")}
                      for k, v in votes.items()}
        })

    vote_result = score_posts_with_audience(
        llm, variants, audience_agents, personality_card, event_callback=vote_cb
    )
    top_ids = vote_result.get("top_ids", [v["id"] for v in variants[:2]])

    print(f"  Top IDs: {top_ids}", file=sys.stderr)
    _emit(state, "audience_vote", "completed", {"top_ids": top_ids})

    return {
        "audience_votes": vote_result.get("agent_votes", {}),
        "aggregated_scores": vote_result.get("aggregated", {}),
        "top_post_ids": top_ids,
    }


# ── Node 5: Refine Posts (reuse) ──

def refine_posts_node(state: AdaptationV2State) -> dict:
    print(f"\n{'='*70}\n\033[1m[V2 STEP 5] REFINE TOP POSTS\033[0m\n{'='*70}", file=sys.stderr)
    _emit(state, "refine", "started")

    llm = state.get("_llm") or create_llm(purpose="generation")
    variants = state.get("adaptations", [])
    top_ids = state.get("top_post_ids", [])
    graph = load_graph(state["graph_path"])
    personality_card = get_personality_card(graph)

    refined = []
    for pid in top_ids[:2]:
        post = next((v for v in variants if v["id"] == pid), None)
        if not post:
            continue

        # Build feedback from votes
        feedback = {}
        for aid, votes in state.get("audience_votes", {}).items():
            if pid in votes:
                feedback[aid] = votes[pid]

        result = refine_post_with_feedback(llm, post, feedback, personality_card, state["platform"])
        refined.append(result)
        _emit(state, "refine", "progress", {
            "post_id": pid,
            "original_text": post["text"][:200],
            "refined_text": result.get("refined_text", "")[:200],
        })

    _emit(state, "refine", "completed", {"count": len(refined)})
    print(f"  Refined {len(refined)} posts", file=sys.stderr)

    return {"refined_posts": refined}


# ── Node 6: V2 Quality Filter ──

def v2_quality_filter_node(state: AdaptationV2State) -> dict:
    print(f"\n{'='*70}\n\033[1m[V2 STEP 6] QUALITY FILTER (11-point)\033[0m\n{'='*70}", file=sys.stderr)
    _emit(state, "quality_filter", "started")

    llm = state.get("_llm") or create_llm(purpose="generation")
    refined = state.get("refined_posts", [])
    internalization = state.get("founder_internalization", {})
    dissection = state.get("source_dissection", {})
    all_events = state.get("events_used", [])
    word_range = internalization.get("word_count_range", [150, 300])
    word_range_str = f"{word_range[0]}-{word_range[1]} words" if isinstance(word_range, list) and len(word_range) == 2 else str(word_range)

    prompt_template = _load_prompt("v2_quality_filter")
    quality_results = []

    for r in refined:
        post_text = r.get("refined_text", r.get("text", ""))
        planning = r.get("planning", "Not available")

        prompt = prompt_template.format(
            post_text=post_text,
            hook_promise=planning[:200] if planning else "Not available",
            source_hook_mechanics=json.dumps(dissection.get("hook_mechanics", []), indent=2)[:1000],
            founder_internalization=json.dumps(internalization, indent=2)[:2000],
            events_used_all_variants="\n".join(f"- {e}" for e in all_events) or "None tracked.",
            word_count_range=word_range_str,
        )

        result_text = llm.generate(prompt, temperature=0.1, max_tokens=1500)
        qr = _parse_json(result_text)

        if not qr:
            qr = {"checks": {}, "passed": True, "failures_count": 0}

        passed = qr.get("passed", True)
        failures = qr.get("failures_count", 0)
        print(f"  Post {r.get('id', '?')}: {'PASS' if passed else 'FAIL'} ({failures} failures)", file=sys.stderr)
        if not passed:
            for s in qr.get("rewrite_suggestions", [])[:2]:
                print(f"    → {s[:80]}", file=sys.stderr)

        quality_results.append({
            "post_id": r.get("id", ""),
            "quality": qr,
        })

        _emit(state, "quality_filter", "progress", {
            "post_id": r.get("id", ""),
            "passed": passed,
            "failures": failures,
        })

    _emit(state, "quality_filter", "completed", {"count": len(quality_results)})

    return {"quality_results": quality_results}


# ── Node 7: Track Coverage (reuse) ──

def track_coverage_node(state: AdaptationV2State) -> dict:
    print(f"\n{'='*70}\n\033[1m[V2 STEP 7] TRACK COVERAGE\033[0m\n{'='*70}", file=sys.stderr)
    _emit(state, "track_coverage", "started")

    refined = state.get("refined_posts", [])
    best = refined[0] if refined else {}
    post_text = best.get("refined_text", best.get("text", ""))

    coverage = {}
    if post_text:
        try:
            graph = load_graph(state["graph_path"])
            topic_proxy = state["source_post"].split("\n")[0][:100]
            coverage = track_node_usage(
                post_text, graph, topic_proxy, state["platform"], state["founder_slug"]
            )
        except Exception as e:
            print(f"  \033[33mCoverage tracking failed: {e}\033[0m", file=sys.stderr)

    _emit(state, "track_coverage", "completed", {"coverage": bool(coverage)})
    return {"coverage_result": coverage}


# ── Entry Point ──

def run_v2_adaptation(
    source_post: str,
    platform: str,
    founder_slug: str,
    graph_path: str,
    creativity: float = 0.5,
    event_bus=None,
    num_variants: int = 5,
) -> dict:
    """Run the full V2 Viral Post Adaptation pipeline."""
    print(f"\n{'#'*70}\n\033[1;35m[V2 ADAPTATION PIPELINE] Starting\033[0m\n{'#'*70}", file=sys.stderr)

    viral_graph_path = get_viral_graph_path()

    state: AdaptationV2State = {
        "source_post": source_post,
        "platform": platform,
        "founder_slug": founder_slug,
        "creativity": creativity,
        "num_variants": min(num_variants, 5),
        "graph_path": graph_path,
        "viral_graph_path": viral_graph_path,
        "founder_internalization": {},
        "source_dissection": {},
        "adaptations": [],
        "events_used": [],
        "audience_votes": {},
        "aggregated_scores": {},
        "top_post_ids": [],
        "refined_posts": [],
        "quality_results": [],
        "coverage_result": {},
        "traceability": {},
        "agent_log": [],
        "_event_bus": event_bus,
        "_llm": None,
        "_founder_ctx": {},
    }

    # Run nodes sequentially
    nodes = [
        ("internalize_founder", internalize_founder_node),
        ("dissect_source", dissect_source_node),
        ("generate_adaptations", generate_adaptations_node),
        ("audience_vote", audience_vote_node),
        ("refine_posts", refine_posts_node),
        ("quality_filter", v2_quality_filter_node),
        ("track_coverage", track_coverage_node),
    ]

    for name, fn in nodes:
        try:
            updates = fn(state)
            if updates:
                state.update(updates)
        except Exception as e:
            print(f"\033[31m[V2] Node '{name}' failed: {e}\033[0m", file=sys.stderr)
            logger.exception(f"V2 node {name} failed")
            _emit(state, name, "error", {"error": str(e)})

    # Emit done
    refined = state.get("refined_posts", [])
    best = refined[0] if refined else {}
    best_text = best.get("refined_text", best.get("text", ""))

    if not best_text and state.get("adaptations"):
        best_text = state["adaptations"][0].get("text", "")

    done_data = {
        "original": source_post,
        "customized": best_text,
        "topic": source_post.split("\n")[0][:100],
        "all_variants": [
            {"id": v["id"], "engine_name": v["engine_name"], "text": v["text"][:300],
             "word_count": v.get("word_count", 0)}
            for v in state.get("adaptations", [])
        ],
        "audience_votes": {
            k: {pk: {"score": pv.get("score", 5), "feedback": pv.get("feedback", "")}
                for pk, pv in v.items()}
            for k, v in state.get("audience_votes", {}).items()
        },
        "aggregated_scores": state.get("aggregated_scores", {}),
        "top_ids": state.get("top_post_ids", []),
        "refined_posts": [
            {"id": r.get("id", ""), "original_text": r.get("original_text", "")[:200],
             "refined_text": r.get("refined_text", "")[:200]}
            for r in refined
        ],
        "quality": state.get("quality_results", [{}])[0].get("quality", {}) if state.get("quality_results") else {},
        "sections": {},
        "founder_context": {
            "beliefs_count": len(state.get("_founder_ctx", {}).get("beliefs", [])),
            "personality_card_length": len(state.get("_founder_ctx", {}).get("personality_card", "")),
        },
        "viral_context": {},
        "traceability": state.get("traceability", {}),
        "founder_internalization": state.get("founder_internalization", {}),
        "source_dissection": state.get("source_dissection", {}),
        "events_used": state.get("events_used", []),
        "v2_quality": state.get("quality_results", []),
    }

    _emit(state, "done", "pipeline_done", done_data)

    print(f"\n\033[32m[V2 ADAPTATION PIPELINE] Done: {len(best_text)} chars\033[0m", file=sys.stderr)
    return done_data
