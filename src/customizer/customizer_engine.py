"""Post customization engine — per-section creativity-weighted transformation."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ..config.founders import get_active_founder, get_viral_graph_path
from ..generation.creativity import build_creativity_instructions, creativity_to_temperature
from ..graph.query import get_full_context
from ..graph.store import load_graph
from ..graph.viral_query import get_viral_context_for_topic, format_viral_context_for_prompt
from ..llm.factory import create_llm
from .section_splitter import PostSections, split_post

logger = logging.getLogger(__name__)

# ── Prompt loader ────────────────────────────────────────────────────────────

PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    """Load a prompt template from the prompts/ folder.

    Args:
        name: Filename without extension, e.g. "section_transform".

    Returns:
        The raw prompt string with {placeholders} intact.

    Raises:
        FileNotFoundError: If the .txt file does not exist in PROMPTS_DIR.
    """
    path = PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {path}\n"
            f"Expected a file named '{name}.txt' inside {PROMPTS_DIR}"
        )
    return path.read_text(encoding="utf-8")


# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class SectionCreativity:
    opening: float = 0.5
    body: float = 0.5
    closing: float = 0.5
    tone: float = 0.5


@dataclass
class CustomizationResult:
    original: str
    customized: str
    sections: dict = field(default_factory=dict)
    founder_context: dict = field(default_factory=dict)
    viral_context: dict = field(default_factory=dict)
    topic: str = ""
    traceability: dict = field(default_factory=dict)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _extract_topic(content: str, llm=None) -> str:
    """Extract the main topic from a post. Uses LLM if available, else keyword fallback."""
    if llm:
        try:
            prompt_template = load_prompt("extract_topic")
            prompt = prompt_template.format(content=content[:1000])
            topic = llm.generate(prompt, temperature=0.1, max_tokens=20).strip()
            if topic and len(topic) < 100:
                return topic
        except Exception:
            pass

    # Fallback: extract frequent meaningful words
    stopwords = {"the", "and", "but", "for", "are", "was", "with", "that", "this", "have",
                 "from", "not", "you", "your", "they", "their", "about", "just", "been",
                 "more", "than", "when", "what", "who", "how", "all", "can", "will", "one",
                 "our", "out", "its", "also", "most", "into", "over", "some", "very", "don"}
    words = [w.lower().strip(".,!?\"'()[]") for w in content.split() if len(w) > 3]
    meaningful = [w for w in words if w not in stopwords]
    return " ".join(meaningful[:5]) if meaningful else "general"


def _build_founder_history(founder_ctx: dict) -> str:
    """Extract and format the founder's specific historical context/stories."""
    stories = founder_ctx.get("stories", [])
    if not stories:
        return "No specific history or past work provided."
    
    text = ""
    for s in stories[:5]:
        text += f"- {s.get('title', 'Experience')}: {s.get('content', '')}\n"
    return text.strip()


def _get_creativity_instruction(creativity: float) -> str:
    if creativity <= 0.2:
        return "KEEP ALMOST EVERYTHING. Only swap specific words/phrases to match the founder's vocabulary. Structure stays identical."
    elif creativity <= 0.5:
        return "ADAPT THE VOICE. Keep the key points and structure but rewrite in the founder's natural style and rhythm."
    elif creativity <= 0.8:
        return "SIGNIFICANTLY REWRITE. Keep the core message/topic but change structure, examples, and phrasing to match the founder."
    else:
        return "FULL CREATIVE REWRITE. Use the topic/theme as a seed but create entirely new content in the founder's voice, using their beliefs and stories."


def _creativity_label(value: float) -> str:
    """Human-readable label for a creativity percentage, used in variant prompts."""
    if value < 0.2:
        return "(keep almost identical)"
    if value > 0.7:
        return "(rewrite freely)"
    return "(adapt voice)"


def _transform_section(
    section_text: str,
    section_name: str,
    creativity: float,
    founder_ctx: dict,
    viral_ctx: dict,
    llm,
) -> str:
    """Transform a single section at the given creativity level."""
    if not section_text.strip():
        return section_text

    # Build viral context block
    viral_block = ""
    if viral_ctx:
        viral_text = format_viral_context_for_prompt(viral_ctx, creativity)
        viral_block = f"## VIRAL PATTERNS (for reference)\n{viral_text}"

    beliefs_text = "\n".join(
        f"- {b.get('topic', '?')}: {b.get('stance', '?')}"
        for b in founder_ctx.get("beliefs", [])[:8]
    ) or "No specific beliefs."

    style_text = "\n".join(
        f"- [{r.get('rule_type', '?')}] {r.get('description', '')}"
        for r in founder_ctx.get("style_rules", [])[:10]
    ) or "No specific rules."

    vocab = founder_ctx.get("vocabulary", {})

    prompt_template = load_prompt("section_transform")
    prompt = prompt_template.format(
        section_name=section_name.upper(),
        section_text=section_text,
        creativity_pct=int(creativity * 100),
        creativity_instruction=_get_creativity_instruction(creativity),
        personality_card=founder_ctx.get("personality_card", "Not available.")[:2000],
        founder_context=_build_founder_history(founder_ctx),
        beliefs=beliefs_text,
        style_rules=style_text,
        phrases_used=", ".join(vocab.get("phrases_used", [])) or "None",
        phrases_never=", ".join(vocab.get("phrases_never", [])) or "None",
        viral_block=viral_block,
    )

    temperature = creativity_to_temperature(creativity)
    result = llm.generate(prompt, temperature=temperature, max_tokens=2000)
    return result.strip()


# ── Simple customizer ─────────────────────────────────────────────────────────

def customize_post(
    original_text: str,
    founder_slug: str,
    creativity: SectionCreativity,
    platform: str = "linkedin",
) -> CustomizationResult:
    """Customize a post for a founder with per-section creativity control."""
    print(f"\n{'='*60}\n\033[1m[Customizer] Starting post customization\033[0m\n{'='*60}", file=sys.stderr, flush=True)
    print(f"  Founder: {founder_slug}", file=sys.stderr, flush=True)
    print(f"  Creativity: opening={creativity.opening:.0%}, body={creativity.body:.0%}, closing={creativity.closing:.0%}, tone={creativity.tone:.0%}", file=sys.stderr, flush=True)
    print(f"  Post length: {len(original_text)} chars", file=sys.stderr, flush=True)

    # Split post
    sections = split_post(original_text)
    print(f"  Sections: opening={len(sections.opening)} body={len(sections.body)} closing={len(sections.closing)} chars", file=sys.stderr, flush=True)

    # Load LLM
    llm = create_llm(purpose="generation")

    # Extract topic
    topic = _extract_topic(original_text, llm)
    print(f"  Topic: \"{topic}\"", file=sys.stderr, flush=True)

    # Load founder context
    from ..config.founders import get_founder_paths
    import yaml
    config_path = Path(__file__).parent.parent.parent / "config" / "llm-config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    paths = get_founder_paths(config, founder_slug)
    graph = load_graph(paths["graph_path"])
    founder_ctx = get_full_context(graph, topic, platform)

    # Load viral context
    viral_ctx = {}
    vgp = get_viral_graph_path()
    if Path(vgp).exists():
        viral_graph = load_graph(vgp)
        if viral_graph.number_of_nodes() > 0:
            viral_ctx = get_viral_context_for_topic(viral_graph, topic, creativity.tone)

    # Transform each section
    result_sections = {}

    for section_name, section_text, section_creativity in [
        ("opening", sections.opening, creativity.opening),
        ("body", sections.body, creativity.body),
        ("closing", sections.closing, creativity.closing),
    ]:
        if not section_text.strip():
            result_sections[section_name] = {"original": "", "customized": ""}
            continue

        if section_creativity <= 0.05:
            print(f"  [{section_name}] Keeping verbatim (creativity={section_creativity:.0%})", file=sys.stderr, flush=True)
            result_sections[section_name] = {"original": section_text, "customized": section_text}
        else:
            print(f"  [{section_name}] Transforming (creativity={section_creativity:.0%})...", file=sys.stderr, flush=True)
            customized = _transform_section(section_text, section_name, section_creativity, founder_ctx, viral_ctx, llm)
            result_sections[section_name] = {"original": section_text, "customized": customized}
            print(f"  [{section_name}] → {len(section_text)} → {len(customized)} chars", file=sys.stderr, flush=True)

    # Reassemble
    customized_parts = [
        result_sections["opening"]["customized"],
        result_sections["body"]["customized"],
        result_sections["closing"]["customized"],
    ]
    customized_text = "\n\n".join(p for p in customized_parts if p.strip())

    print(f"\033[32m[Customizer] Done: {len(original_text)} → {len(customized_text)} chars\033[0m", file=sys.stderr, flush=True)

    return CustomizationResult(
        original=original_text,
        customized=customized_text,
        sections=result_sections,
        founder_context={"beliefs_count": len(founder_ctx.get("beliefs", [])), "style_rules_count": len(founder_ctx.get("style_rules", []))},
        viral_context={"hooks": len(viral_ctx.get("hooks", [])), "patterns": len(viral_ctx.get("patterns", []))},
        topic=topic,
        traceability=founder_ctx.get("traceability", {}),
    )


# ═══════════════════════════════════════════════════════════════
# FULL AGENTIC PIPELINE CUSTOMIZATION
# ═══════════════════════════════════════════════════════════════

CUSTOMIZATION_STRATEGIES = [
    {
        "id": "conservative_voice",
        "name": "Conservative Voice Match",
        "instruction": "Keep the exact structure and key points of the original. Only change vocabulary, phrasing, and tone to match the founder's voice. The reader should recognize this as the same post, just written differently.",
    },
    {
        "id": "moderate_rewrite",
        "name": "Moderate Rewrite",
        "instruction": "Keep the core message and flow but rewrite in the founder's natural style. Use their sentence rhythm, signature phrases, and rhetorical patterns. Add their perspective where it strengthens the argument.",
    },
    {
        "id": "bold_rewrite",
        "name": "Bold Founder Rewrite",
        "instruction": "Keep the topic but rebuild the post using the founder's beliefs and thinking models. The structure can change significantly. Ground the argument in the founder's actual experience and contrarian positions.",
    },
    {
        "id": "story_led",
        "name": "Story-Led Adaptation",
        "instruction": "Rewrite the post by leading with one of the founder's relevant personal stories, then connecting it to the original post's message. The story should prove the point in a way that data alone cannot.",
    },
    {
        "id": "contrarian_take",
        "name": "Contrarian Take",
        "instruction": "Identify what the original post takes for granted and challenge it from the founder's contrarian perspective. Use their 'uncomfortable economic truth' thinking model. The post should make the reader reconsider the original premise.",
    },
]


def _generate_customization_variant(
    original_text: str,
    strategy: dict,
    creativity: SectionCreativity,
    founder_ctx: dict,
    viral_ctx: dict,
    llm,
    platform: str,
) -> dict:
    """Generate one customization variant using a specific strategy."""
    beliefs_text = "\n".join(
        f"- {b.get('topic', '?')}: {b.get('stance', '?')}"
        for b in founder_ctx.get("beliefs", [])[:8]
    ) or "None."

    style_text = "\n".join(
        f"- {r.get('description', '')}"
        for r in founder_ctx.get("style_rules", [])[:10]
    ) or "None."

    vocab = founder_ctx.get("vocabulary", {})
    phrases_used_block = (
        f"## USE THESE PHRASES: {', '.join(vocab['phrases_used'][:8])}"
        if vocab.get("phrases_used") else ""
    )
    phrases_never_block = (
        f"## NEVER USE: {', '.join(vocab['phrases_never'][:8])}"
        if vocab.get("phrases_never") else ""
    )

    viral_block = ""
    if viral_ctx:
        viral_text = format_viral_context_for_prompt(viral_ctx, creativity.tone)
        if viral_text and len(viral_text) > 20:
            viral_block = f"## VIRAL PATTERNS (for structural reference)\n{viral_text[:1500]}"

    prompt_template = load_prompt("generate_variant")
    prompt = prompt_template.format(
        platform=platform,
        strategy_instruction=strategy["instruction"],
        original_text=original_text,
        personality_card=founder_ctx.get("personality_card", "Not available.")[:3000],
        founder_context=_build_founder_history(founder_ctx),
        beliefs=beliefs_text,
        style_rules=style_text,
        phrases_used_block=phrases_used_block,
        phrases_never_block=phrases_never_block,
        viral_block=viral_block,
        opening_pct=int(creativity.opening * 100),
        opening_label=_creativity_label(creativity.opening),
        body_pct=int(creativity.body * 100),
        body_label=_creativity_label(creativity.body),
        closing_pct=int(creativity.closing * 100),
        closing_label=_creativity_label(creativity.closing),
    )

    temperature = creativity_to_temperature(max(creativity.opening, creativity.body, creativity.closing))
    text = llm.generate(prompt, temperature=temperature, max_tokens=llm.max_output_tokens)

    return {
        "id": f"custom_{strategy['id']}_{platform}",
        "text": text.strip(),
        "engine_id": strategy["id"],
        "engine_name": strategy["name"],
        "platform": platform,
    }


def customize_post_full_pipeline(
    original_text: str,
    founder_slug: str,
    creativity: SectionCreativity,
    platform: str = "linkedin",
    event_bus=None,
    num_variants: int = 5,
) -> dict:
    """Full agentic pipeline for post customization.

    Generates 5 variants → audience vote → refine top 2 →
    opening massacre → humanize → quality gate.

    Returns a dict with all pipeline data (variants, votes, refined, final post).
    """
    from ..generation.audience_panel import load_audience_agents, score_posts_with_audience
    from ..generation.opening_line_massacre import (
        apply_winning_opening, generate_opening_lines, score_opening_lines_with_audience,
    )
    from ..generation.refiner import refine_post_with_feedback
    from ..humanization.quality_gate import quality_gate
    from ..langchain_agents.chains import humanize_chain
    from ..graph.query import get_style_rules_for_platform, get_vocabulary_rules
    from ..generation.pipeline_events import PipelineEvent

    def _emit(stage, status, data=None, progress=0.0):
        if event_bus:
            event_bus.emit(PipelineEvent(stage=stage, status=status, data=data or {}, progress=progress))

    print(f"\n{'='*60}\n\033[1m[CustomizerPipeline] Starting full pipeline\033[0m\n{'='*60}", file=sys.stderr, flush=True)
    _emit("customize_start", "started", {"original_length": len(original_text)})

    # ── Step 1: Setup ──
    llm = create_llm(purpose="generation")
    topic = _extract_topic(original_text, llm)
    print(f"  Topic: \"{topic}\"", file=sys.stderr, flush=True)

    import yaml
    config_path = Path(__file__).parent.parent.parent / "config" / "llm-config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    from ..config.founders import get_founder_paths
    paths = get_founder_paths(config, founder_slug)
    graph = load_graph(paths["graph_path"])
    founder_ctx = get_full_context(graph, topic, platform)

    viral_ctx = {}
    vgp = get_viral_graph_path()
    if Path(vgp).exists():
        viral_graph = load_graph(vgp)
        if viral_graph.number_of_nodes() > 0:
            viral_ctx = get_viral_context_for_topic(viral_graph, topic, creativity.tone)

    personality_card = founder_ctx.get("personality_card", "")

    # ── Step 2: Generate N variants ──
    print(f"\n\033[1m[Step 2] Generating {num_variants} customization variants...\033[0m", file=sys.stderr, flush=True)
    _emit("generate_variants", "started", {"total": num_variants})

    variants = []
    strategies_to_use = CUSTOMIZATION_STRATEGIES[:num_variants]
    for i, strategy in enumerate(strategies_to_use):
        print(f"  Variant {i+1}/{num_variants}: {strategy['name']}...", file=sys.stderr, flush=True)
        _emit("generate_variants", "progress", {"index": i, "strategy": strategy["name"]}, progress=(i+1)/num_variants)
        try:
            variant = _generate_customization_variant(
                original_text, strategy, creativity, founder_ctx, viral_ctx, llm, platform
            )
            variants.append(variant)
            print(f"  → {len(variant['text'])} chars", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"  ✗ {strategy['id']} failed: {e}", file=sys.stderr, flush=True)

    _emit("generate_variants", "completed", {"count": len(variants)})

    if not variants:
        return {"error": "All variants failed", "original": original_text, "customized": original_text}

    # ── Step 3: Audience vote ──
    print(f"\n\033[1m[Step 3] Audience voting on {len(variants)} variants...\033[0m", file=sys.stderr, flush=True)
    _emit("audience_vote", "started")

    audience_agents = load_audience_agents()

    def vote_cb(agent_id, agent_name, votes):
        _emit("audience_vote", "progress", {"agent_id": agent_id, "agent_name": agent_name, "votes": {k: {"score": v.get("score", 5), "feedback": v.get("feedback", "")} for k, v in votes.items()}})

    vote_result = score_posts_with_audience(llm, variants, audience_agents, personality_card, event_callback=vote_cb)
    top_ids = vote_result.get("top_ids", [v["id"] for v in variants[:2]])

    _emit("audience_vote", "completed", {"top_ids": top_ids})

    # ── Step 4: Refine top 2 ──
    print(f"\n\033[1m[Step 4] Refining top {len(top_ids[:2])} variants...\033[0m", file=sys.stderr, flush=True)
    _emit("refine", "started")

    refined = []
    feedback_for_refiner = vote_result.get("feedback_for_refiner", {})
    for pid in top_ids[:2]:
        post = next((v for v in variants if v["id"] == pid), None)
        if not post:
            continue
        feedback = feedback_for_refiner.get(pid, {})
        if not feedback:
            for aid, votes in vote_result.get("agent_votes", {}).items():
                if pid in votes:
                    agent_name = votes[pid].get("agent_name", aid)
                    feedback[agent_name] = votes[pid]
        result = refine_post_with_feedback(llm, post, feedback, personality_card, platform)
        refined.append(result)
        _emit("refine", "progress", {"post_id": pid, "original_text": post["text"][:200], "refined_text": result["refined_text"][:200]})

    _emit("refine", "completed", {"count": len(refined)})

    best_refined = refined[0] if refined else {"id": variants[0]["id"], "refined_text": variants[0]["text"], "original_text": variants[0]["text"]}

    # ── Step 5: Opening Line Massacre ──
    print(f"\n\033[1m[Step 5] Opening Line Massacre...\033[0m", file=sys.stderr, flush=True)
    _emit("opening_massacre", "started")

    openings = generate_opening_lines(best_refined["refined_text"], founder_ctx, viral_ctx, llm, n=10)
    _emit("opening_massacre", "generating", {"count": len(openings), "openings": [{"id": o["id"], "text": o["text"]} for o in openings]})

    post_body = "\n\n".join(best_refined["refined_text"].strip().split("\n\n")[1:])
    opening_result = score_opening_lines_with_audience(
        llm, openings, post_body, audience_agents, personality_card,
    )

    winning_opening = opening_result["winning_line"]
    final_text = apply_winning_opening(best_refined["refined_text"], winning_opening)
    _emit("opening_massacre", "completed", {"winning_text": winning_opening["text"]})

    # ── Step 6: Humanize + Quality Gate ──
    print(f"\n\033[1m[Step 6] Humanizing + Quality Gate...\033[0m", file=sys.stderr, flush=True)
    _emit("humanize", "started")

    from ..langchain_agents.llm_adapter import create_langchain_llm
    lc_llm = create_langchain_llm()
    style_rules = get_style_rules_for_platform(graph, platform)
    vocab = get_vocabulary_rules(graph)
    humanized = humanize_chain(lc_llm, final_text, style_rules, vocab)

    _emit("humanize", "completed", {"length": len(humanized)})

    qr = quality_gate(humanized, graph)
    _emit("quality_gate", "completed", {"score": qr["score"], "passed": qr["passed"]})

    print(f"\n\033[32m[CustomizerPipeline] Done: {len(original_text)} → {len(humanized)} chars, quality={qr['score']}%\033[0m", file=sys.stderr, flush=True)

    return {
        "original": original_text,
        "customized": humanized,
        "topic": topic,
        "all_variants": [{"id": v["id"], "engine_name": v["engine_name"], "text": v["text"][:300]} for v in variants],
        "audience_votes": {k: {pk: {"score": pv.get("score", 5), "feedback": pv.get("feedback", "")} for pk, pv in v.items()} for k, v in vote_result.get("agent_votes", {}).items()},
        "aggregated_scores": vote_result.get("aggregated", {}),
        "top_ids": top_ids,
        "refined_posts": [{"id": r["id"], "original_text": r["original_text"][:200], "refined_text": r["refined_text"][:200]} for r in refined],
        "opening_lines": [{"id": o["id"], "text": o["text"]} for o in openings],
        "winning_opening": {"text": winning_opening["text"]},
        "quality": {"score": qr["score"], "passed": qr["passed"]},
        "sections": {},
        "founder_context": {"beliefs_count": len(founder_ctx.get("beliefs", [])), "personality_card_length": len(personality_card)},
        "viral_context": {"hooks": len(viral_ctx.get("hooks", [])), "patterns": len(viral_ctx.get("patterns", []))},
        "traceability": founder_ctx.get("traceability", {}),
    }

# ── API Feature Endpoints ───────────────────────────────────────────────────

def quick_fix_post(topic: str, founder_slug: str, platform: str, creativity: float) -> str:
    """Generate a fast variant bypassing the voting consensus pipeline."""
    llm = create_llm(purpose="generation")
    import yaml
    config_path = Path(__file__).parent.parent.parent / "config" / "llm-config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    from ..config.founders import get_founder_paths
    paths = get_founder_paths(config, founder_slug)
    graph = load_graph(paths["graph_path"])
    
    from ..graph.query import get_merged_context
    viral_graph = load_graph(get_viral_graph_path()) if Path(get_viral_graph_path()).exists() else None
    context = get_merged_context(graph, viral_graph, topic, platform, creativity)
    
    from ..generation.narrative_engines import NARRATIVE_ENGINES, generate_with_engine
    engine = NARRATIVE_ENGINES[0]
    narrative = {"narrative": topic, "angle": f"Write defensively about {topic}", "hook": topic}
    post = generate_with_engine(engine, narrative, platform, context, llm)
    
    from ..langchain_agents.chains import humanize_chain
    from ..graph.query import get_style_rules_for_platform, get_vocabulary_rules
    humanized = humanize_chain(llm, post["text"], get_style_rules_for_platform(graph, platform), get_vocabulary_rules(graph))
    return humanized

def regenerate_with_context(previous_post: str, feedback: str, founder_slug: str, platform: str, creativity: float) -> str:
    """Regenerate an entire post with feedback using existing block as context."""
    llm = create_llm(purpose="generation")
    import yaml
    config_path = Path(__file__).parent.parent.parent / "config" / "llm-config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    from ..config.founders import get_founder_paths
    paths = get_founder_paths(config, founder_slug)
    graph = load_graph(paths["graph_path"])
    topic = _extract_topic(previous_post, llm)
    founder_ctx = get_full_context(graph, topic, platform)
    
    prompt_template = load_prompt("regenerate_with_context")
    prompt = prompt_template.format(
        platform=platform,
        feedback=feedback,
        previous_post=previous_post,
        personality_card=founder_ctx.get('personality_card', '')[:2000],
        founder_context=_build_founder_history(founder_ctx)
    )
    result = llm.generate(prompt, temperature=0.7, max_tokens=2000)
    return result.strip()

def rewrite_section(entire_post: str, section_text: str, command: str, founder_slug: str, platform: str) -> str:
    """Rewrite a specific highlighted slice of text based on user command within the post flow."""
    llm = create_llm(purpose="generation")
    import yaml
    config_path = Path(__file__).parent.parent.parent / "config" / "llm-config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    from ..config.founders import get_founder_paths
    paths = get_founder_paths(config, founder_slug)
    graph = load_graph(paths["graph_path"])
    topic = _extract_topic(entire_post, llm)
    founder_ctx = get_full_context(graph, topic, platform)
    
    prompt_template = load_prompt("rewrite_section")
    prompt = prompt_template.format(
        platform=platform,
        command=command,
        entire_post=entire_post,
        section_text=section_text,
        personality_card=founder_ctx.get('personality_card', '')[:2000],
        founder_context=_build_founder_history(founder_ctx)
    )
    result = llm.generate(prompt, temperature=0.7, max_tokens=1000)
    return result.strip()