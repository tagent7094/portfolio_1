"""Narrative engines for diverse post generation.

Each engine defines a distinct structural approach to building a post.
Engines are designed to produce meaningfully different outputs —
not just different openings on the same structure.

Enhanced with anti-slop instructions baked into each engine's structural guidance.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from ..utils.text_utils import load_prompt, fill_prompt

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

NARRATIVE_ENGINES = [
    {
        "id": "bold_declarative",
        "name": "Bold Declarative + Evidence Stack",
        "structural_instruction": (
            "Open with a bold, specific, declarative statement that takes a clear stance. "
            "Not a generic claim — a claim with a number, a name, or a timeframe attached. "
            "Follow with 2-3 pieces of concrete evidence: real metrics, specific case studies, "
            "or named personal experiences (not hypotheticals). "
            "Close with a verdict that reinforces the opening claim in different words. "
            "No hedging, no 'it depends,' no qualifiers that soften the thesis. "
            "The post should read like a closing argument, not an exploration."
        ),
    },
    {
        "id": "story_first",
        "name": "Story First + Lived Experience Pivot",
        "structural_instruction": (
            "Open IN THE MIDDLE of a specific personal moment — not 'I once had an experience,' "
            "but drop the reader into the scene: a specific place, time, conversation, or decision point. "
            "Build tension through the story: what was at stake, what went wrong or surprised you. "
            "Pivot to the broader insight in the final third — but let the story do the arguing. "
            "The lesson should feel DISCOVERED through the story, not stated and then illustrated. "
            "Include at least one line of real dialogue or a specific detail only someone who lived it would know."
        ),
    },
    {
        "id": "concession_counter",
        "name": "Concession Then Counter + Verdict",
        "structural_instruction": (
            "Start by genuinely conceding the STRONGEST version of the opposing argument. "
            "Not a strawman — the version a smart opponent would actually make. "
            "The concession must feel honest: 'they're right about X, and here's why.' "
            "THEN counter with evidence, experience, or logic that flips the framing. "
            "The counter must be specific: a real example, a real number, a real outcome. "
            "End with a clear verdict — not 'both sides have a point' but a definitive position. "
            "The structural rhythm: agree, agree, BUT, evidence, verdict."
        ),
    },
    {
        "id": "data_drop",
        "name": "Data Drop + Reframe",
        "structural_instruction": (
            "Open with a specific, surprising number or data point that stops the scroll. "
            "The number should be real and verifiable — not rounded, not vague ('over 50%'). "
            "Then reframe what that data ACTUALLY means — challenge the interpretation "
            "that most people would have at first glance. "
            "The reframe is the insight: 'everyone sees this number and thinks X, but it actually means Y.' "
            "Close with the implication: what should the reader do or think differently? "
            "The data does the work — don't over-explain it."
        ),
    },
    {
        "id": "earned_contrarian",
        "name": "Earned Contrarian (Not Hot Take)",
        "structural_instruction": (
            "Lead with an opinion that goes against mainstream consensus in your domain. "
            "CRITICAL: This is NOT a 'hot take' or 'unpopular opinion' — those are lazy framings. "
            "The contrarian position must be EARNED through specific experience. "
            "Structure: State the contrarian view plainly (no 'unpopular opinion:' prefix). "
            "Then back it with the specific experience that earned you the right to say this. "
            "Address why the mainstream view exists and why it's wrong or incomplete. "
            "The tone is confident but not arrogant — you're sharing what you've learned, "
            "not declaring everyone else is stupid."
        ),
    },
    {
        "id": "micro_story_stack",
        "name": "Micro-Story Stack (3 vignettes → 1 insight)",
        "structural_instruction": (
            "Structure as exactly 3 very short vignettes (2-3 sentences each) that share a hidden pattern. "
            "Each vignette is a specific, concrete micro-story: a moment, a conversation, a decision. "
            "Don't explain the connection between them — let the reader discover it. "
            "After the third vignette, land the insight in 1-2 sentences: the pattern that connects all three. "
            "The power comes from the accumulation: each story alone is interesting, "
            "but together they prove something. "
            "No transitions between vignettes — just white space. The structural silence IS the transition."
        ),
    },
    {
        "id": "tension_bridge",
        "name": "Tension Bridge (two truths in conflict)",
        "structural_instruction": (
            "Open by naming two things that are BOTH true but appear to contradict each other. "
            "This creates immediate cognitive tension the reader needs resolved. "
            "Spend the body of the post building the bridge — how both can be true simultaneously. "
            "The insight is the reconciliation: a framework, a distinction, or a nuance "
            "that most people miss because they think in either/or. "
            "Close with the practical implication of holding both truths at once. "
            "This structure works best for topics where the mainstream debate is polarized."
        ),
    },
    {
        "id": "before_after",
        "name": "Before/After Transformation",
        "structural_instruction": (
            "Paint the 'before' state vividly: the specific pain, confusion, or old way of thinking. "
            "Use concrete details — not 'things were hard' but 'I was spending 6 hours a week on X and getting Y results.' "
            "Then show the 'after' state with equally specific results. "
            "CRITICAL: The transformation must feel EARNED, not magical. "
            "Include the specific action, insight, or decision that caused the shift. "
            "This isn't 'and then everything changed' — it's 'and then I did THIS specific thing and here's exactly what happened.' "
            "The post fails if the transformation could be an ad."
        ),
    },
    {
        "id": "question_interrogation",
        "name": "Question Interrogation (not question hook)",
        "structural_instruction": (
            "Open with a question that the reader thinks they know the answer to — then systematically "
            "dismantle the obvious answer. This is NOT a rhetorical question hook ('Isn't it crazy that...?'). "
            "The question must be genuine: something you actually struggled with. "
            "Walk through why the obvious answers are wrong or incomplete, using specific evidence. "
            "Arrive at the real answer — which should surprise. "
            "The structure: question → obvious answer → why it's wrong → real answer → proof. "
            "The gap between the obvious answer and the real answer IS the insight."
        ),
    },
    {
        "id": "anti_post",
        "name": "The Anti-Post (weaponized plainness)",
        "structural_instruction": (
            "Write the opposite of a typical LinkedIn post. No dramatic hook, no 'I learned X' structure, "
            "no performative vulnerability, no inspirational closer. "
            "Instead: state something useful, specific, and non-obvious in plain, direct language. "
            "The tone is casual, almost throwaway — as if the person is sharing a thought, "
            "not performing content creation. "
            "This works because it's disarming: on a platform full of performative energy, "
            "genuine plainness stands out. "
            "Keep it SHORT (under 100 words ideally). "
            "The post should feel like a text message from a smart friend, not a LinkedIn post."
        ),
    },
]


def _format_rules(rules: list[dict], rule_type: str) -> str:
    """Format style rules of a specific type into a string."""
    matching = [r for r in rules if r.get("rule_type") == rule_type]
    return "\n".join(f"- {r.get('description', '')}" for r in matching) or "No specific rules."


def get_engine_by_id(engine_id: str) -> dict | None:
    """Look up a narrative engine by ID."""
    return next((e for e in NARRATIVE_ENGINES if e["id"] == engine_id), None)


def get_engines_subset(engine_ids: list[str] | None = None, n: int | None = None) -> list[dict]:
    """Get a subset of engines by IDs or count.

    If engine_ids is provided, returns those specific engines.
    If n is provided, returns the first n engines.
    If neither, returns all engines.
    """
    if engine_ids:
        return [e for e in NARRATIVE_ENGINES if e["id"] in engine_ids]
    if n:
        return NARRATIVE_ENGINES[:n]
    return NARRATIVE_ENGINES


def generate_with_engine(
    engine: dict,
    narrative: dict,
    platform: str,
    context: dict,
    llm,
    token_callback=None,
) -> dict:
    """Generate a single post using a specific narrative engine.

    Uses the generate_post.txt template with the engine's
    structural_instruction injected as the strategy.
    """
    template = load_prompt(PROMPTS_DIR / "generate_post.txt")

    beliefs_text = "\n".join(
        f"- {b.get('topic', '?')}: {b.get('stance', '?')}"
        for b in context.get("beliefs", [])[:10]
    ) or "No specific beliefs."

    stories_text = "\n".join(
        f"- {s.get('title', '?')}: {s.get('summary', '?')}"
        for s in context.get("stories", [])[:5]
    ) or "No specific stories."

    style_rules = context.get("style_rules", [])
    vocab = context.get("vocabulary", {})

    anti_patterns = "\n".join(
        f"- NEVER: {r['anti_pattern']}" for r in style_rules if r.get("anti_pattern")
    ) or "None specified."

    # Viral context block
    viral_block = context.get("viral_context_block", "")

    # Build narrative text — include post_architecture_hint if available
    narrative_text = narrative.get("narrative", "") + "\n" + narrative.get("angle", "")
    if narrative.get("post_architecture_hint"):
        narrative_text += f"\n\nStructural hint: {narrative['post_architecture_hint']}"

    prompt = fill_prompt(
        template,
        platform=platform,
        personality_card=context.get("personality_card") or "Not available.",
        narrative=narrative_text,
        beliefs=beliefs_text,
        stories=stories_text,
        strategy=engine["structural_instruction"],
        viral_context_block=viral_block,
        opening_rules=_format_rules(style_rules, "opening"),
        closing_rules=_format_rules(style_rules, "closing"),
        rhythm_rules=_format_rules(style_rules, "rhythm"),
        phrases_used=", ".join(vocab.get("phrases_used", [])) or "None.",
        phrases_never=", ".join(vocab.get("phrases_never", [])) or "None.",
        punctuation_rules=_format_rules(style_rules, "punctuation"),
        pronoun_rules=json.dumps(vocab.get("pronoun_rules", {})),
        platform_rules=f"Platform: {platform}",
        anti_patterns=anti_patterns,
    )

    from ..llm.base import LLMProvider

    print(f"\n\033[34m{'='*60}\033[0m", file=sys.stderr)
    print(
        f"\033[34m[NarrativeEngine]\033[0m \033[1m{engine['name']} ({engine['id']})\033[0m "
        f"— prompt={len(prompt)} chars",
        file=sys.stderr,
    )
    print(f"\033[34m{'='*60}\033[0m", file=sys.stderr)

    if isinstance(llm, LLMProvider):
        tokens = []
        for token in llm.generate_stream(prompt, temperature=0.8, max_tokens=llm.max_output_tokens):
            tokens.append(token)
            if token_callback:
                token_callback(token)
        text = "".join(tokens)
    else:
        from langchain_core.messages import HumanMessage
        tokens = []
        try:
            for chunk in llm.stream([HumanMessage(content=prompt)]):
                token = chunk.content
                if token:
                    tokens.append(token)
                    if token_callback:
                        token_callback(token)
            text = "".join(tokens)
        except Exception:
            response = llm.invoke([HumanMessage(content=prompt)])
            text = response.content

    print(
        f"\033[34m[NarrativeEngine]\033[0m \033[32m→ {engine['name']}: "
        f"{len(text)} chars generated\033[0m",
        file=sys.stderr, flush=True,
    )

    return {
        "id": f"{engine['id']}_{platform}",
        "text": text.strip(),
        "engine_id": engine["id"],
        "engine_name": engine["name"],
        "platform": platform,
    }
