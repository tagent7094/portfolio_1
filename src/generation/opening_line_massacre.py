"""Opening Line Massacre v2 — generate raw, human-sounding openings that don't smell like AI."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from statistics import mean

from ..utils.json_parser import parse_llm_json
from ..utils.text_utils import load_prompt, fill_prompt

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

# ─────────────────────────────────────────────────────────
# AI-SLOP PATTERNS — if a generated hook matches these,
# it gets auto-penalized or regenerated
# ─────────────────────────────────────────────────────────
AI_SLOP_PATTERNS = [
    "in today's fast-paced",
    "in the world of",
    "let me tell you",
    "here's the thing",
    "here's what nobody tells you",
    "hot take:",
    "unpopular opinion:",
    "let that sink in",
    "read that again",
    "i'll say it louder",
    "can we talk about",
    "it's time we talked about",
    "the truth about",
    "the secret to",
    "what if i told you",
    "imagine this",
    "picture this",
    "buckle up",
    "spoiler alert",
    "plot twist",
    "game changer",
    "here's why",
    "stop what you're doing",
    "this changed everything",
    "i used to think",  # only slop when followed by generic pivot
    "let's be honest",
    "real talk",
    "hard truth",
    "controversial opinion",
    "most people don't realize",
    "nobody is talking about",
    "the biggest mistake",
    "i'm going to be brutally honest",
    "a thread 🧵",
]


def _is_slop(text: str) -> bool:
    """Check if an opening line matches known AI-slop patterns."""
    lower = text.lower().strip()
    for pattern in AI_SLOP_PATTERNS:
        if lower.startswith(pattern) or pattern in lower[:80]:
            return True
    emoji_count = sum(1 for c in text if ord(c) > 0x1F600)
    if emoji_count > 2:
        return True
    return False


def _slop_score_penalty(text: str) -> float:
    """Return a penalty value (0 to -3) based on how AI-generic the hook sounds."""
    lower = text.lower().strip()
    penalty = 0.0
    for pattern in AI_SLOP_PATTERNS:
        if pattern in lower[:100]:
            penalty -= 1.0
    if text.count("!") > 1:
        penalty -= 0.5
    if text and ord(text[0]) > 0x1F600:
        penalty -= 0.3
    # Generic "I" + past tense + vague object ("I realized something")
    if lower.startswith("i ") and any(w in lower[:40] for w in ["realized", "learned", "discovered", "noticed"]):
        if not any(specific in lower[:80] for specific in ["$", "%", "million", "fired", "quit", "failed", "lost", "broke"]):
            penalty -= 0.5
    return max(penalty, -3.0)


# ─────────────────────────────────────────────────────────
# HOOK STRATEGIES
# ─────────────────────────────────────────────────────────

HOOK_STRATEGIES = [
    {
        "id": "mid_story_drop",
        "name": "Mid-story drop-in",
        "instruction": "Start in the MIDDLE of a specific moment. No setup, no context. The reader walks into a scene already happening. Use a concrete sensory detail — a place, a sound, a number on a screen, a sentence someone said to you.",
        "examples": [
            "My cofounder slid his laptop across the table and said 'look at this number.'",
            "The Slack notification came at 2:47 AM. It was from our biggest client.",
            "I was rewriting the same slide for the fourth time when my phone buzzed.",
        ],
    },
    {
        "id": "specificity_bomb",
        "name": "Specificity bomb",
        "instruction": "Lead with an absurdly specific detail — a number, a date, a name, an amount. Specificity = credibility = curiosity. The reader thinks 'why THAT number?' and keeps reading.",
        "examples": [
            "We lost $43,000 in 11 days because of one Zapier automation.",
            "The doc was 14 pages. The feedback was 3 words: 'start over completely.'",
            "Day 312 of building in public. Here's what nobody claps for.",
        ],
    },
    {
        "id": "earned_contradiction",
        "name": "Earned contradiction",
        "instruction": "State something that sounds wrong but you can back up with experience. NOT a generic contrarian take — it has to be something you earned the right to say through doing the work.",
        "examples": [
            "Our best quarter started the week I stopped looking at our metrics dashboard.",
            "I hire slower since I started ignoring resumes entirely.",
            "The feature our users begged for nearly killed our retention.",
        ],
    },
    {
        "id": "overheard_dialogue",
        "name": "Overheard dialogue",
        "instruction": "Open with something someone actually said — in a meeting, on a call, in a DM. Real human speech is immediately engaging because it's concrete and implies a story. Use quotation marks.",
        "examples": [
            "'You're not ready for enterprise.' — the exact words from our first lost deal.",
            "My investor texted me: 'Are you sure about this pivot?'",
            "'Just make it go viral' — actual feedback I got from a VP last Tuesday.",
        ],
    },
    {
        "id": "tension_gap",
        "name": "Tension / gap opener",
        "instruction": "Create tension between two things — what you expected vs what happened, what everyone says vs what you found, what looks good on paper vs what it feels like. The gap between the two is what pulls the reader in.",
        "examples": [
            "On paper, we had product-market fit. In reality, we had polite users who never came back.",
            "Everyone told me to raise a Series A. My bank account said I should get a job.",
            "The dashboard showed 40% growth. The support inbox told a different story.",
        ],
    },
    {
        "id": "casual_confession",
        "name": "Casual confession (real cost)",
        "instruction": "Admit something that actually costs you something to say — not fake vulnerability where the 'confession' makes you look good. The reader should feel slight discomfort on your behalf. Keep the tone casual, not dramatic.",
        "examples": [
            "I mass-deleted 6 months of my own LinkedIn posts last week. Most of them were embarrassing.",
            "I've been building this product for a year and I still can't explain what it does in one sentence.",
            "Honest moment: I have no idea if our pricing is right. We just picked numbers that felt okay.",
        ],
    },
    {
        "id": "raw_number",
        "name": "Naked number",
        "instruction": "Just the number. Or the number and barely any context. Let the number do the work. No adjectives, no 'incredible' or 'shocking.' The starkness IS the hook.",
        "examples": [
            "0 revenue. 14 months. 3 pivots. Here's what survived.",
            "2,847 cold emails. 11 replies. 1 customer.",
            "We spent $120K on ads last quarter. ROI was negative.",
        ],
    },
    {
        "id": "broken_expectation",
        "name": "Broken pattern / expectation",
        "instruction": "Start a sentence the reader thinks they can finish, then break it. The setup sounds familiar; the landing is unexpected.",
        "examples": [
            "I finally hit my revenue goal and immediately felt worse.",
            "We got featured in TechCrunch and our signups dropped.",
            "After 5 years of building startups, my biggest skill is knowing when to quit.",
        ],
    },
    {
        "id": "micro_moment",
        "name": "Micro-moment zoom",
        "instruction": "Zoom into one tiny, vivid moment — a few seconds of real life. Not a summary, not a lesson, just the moment itself. The smallness of the detail makes it feel real.",
        "examples": [
            "I watched the cursor blink on an empty Google Doc for 20 minutes before I typed the first word of our layoff email.",
            "The Figma file had 47 frames. The client picked frame 2, which took me eight minutes.",
            "I closed my laptop at 11pm, opened my phone, and found myself reading my own product's error page.",
        ],
    },
    {
        "id": "anti_hook",
        "name": "Anti-hook (weaponized plainness)",
        "instruction": "Deliberately boring, flat, or understated. No drama, no setup. The plainness itself is disarming on a platform full of performative energy. Works best when the content that follows is substantial.",
        "examples": [
            "Here's something boring that made us a lot of money.",
            "This isn't a sexy post. It's about spreadsheets.",
            "Nothing viral happened this week. But something useful did.",
        ],
    },
]


def _build_strategy_block(n: int) -> str:
    """Build the numbered hook strategy descriptions for the generation prompt."""
    block = ""
    for i, s in enumerate(HOOK_STRATEGIES[:n], 1):
        examples_str = "\n".join(f'    e.g. "{ex}"' for ex in s["examples"])
        block += (
            f"\n{i}. {s['name']}  (id: {s['id']})\n"
            f"   {s['instruction']}\n"
            f"{examples_str}\n"
        )
    return block


def _build_viral_block(viral_context: dict | None) -> str:
    """Build the optional viral-hooks inspiration block."""
    if not viral_context:
        return ""
    hooks = viral_context.get("hooks", [])
    if not hooks:
        return ""
    lines = [f"- {h.get('hook_name', '')}: {h.get('template', '')}" for h in hooks[:4]]
    return (
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "VIRAL HOOKS FROM YOUR NICHE (steal the structure, not the words)\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        + "\n".join(lines)
    )


# ─────────────────────────────────────────────────────────
# GENERATION
# ─────────────────────────────────────────────────────────

def _build_generation_prompt(
    current_opening: str,
    post_body: str,
    personality: str,
    viral_context: dict | None,
    n: int,
    platform: str = "linkedin",
) -> str:
    """Fill the opening_generation.txt template with runtime values."""
    template = load_prompt(PROMPTS_DIR / "opening_generation.txt")
    return fill_prompt(template, **{
        "n": n,
        "current_opening": current_opening,
        "post_body": post_body[:600],
        "viral_block": _build_viral_block(viral_context),
        "personality": personality[:400] if personality else "Not provided.",
        "strategy_block": _build_strategy_block(n),
        "platform": platform,
    })


def generate_opening_lines(
    post_text: str,
    context: dict,
    viral_context: dict | None,
    llm,
    n: int = 10,
    platform: str = "linkedin",
    max_tokens: int = 2500,
    thinking_budget: int | None = None,
) -> list[dict]:
    """Generate N alternative opening lines for a post with anti-slop filtering."""
    paragraphs = post_text.strip().split("\n\n")
    current_opening = paragraphs[0] if paragraphs else ""
    post_body = "\n\n".join(paragraphs[1:]) if len(paragraphs) > 1 else ""
    personality = context.get("personality_card", "")

    prompt = _build_generation_prompt(
        current_opening=current_opening,
        post_body=post_body,
        personality=personality,
        viral_context=viral_context,
        n=n,
        platform=platform,
    )

    from ..llm.base import LLMProvider

    print(
        f"\n{'='*60}\n[Opening Line Massacre v2] Generating {n} openings...\n{'='*60}",
        file=sys.stderr,
    )

    if isinstance(llm, LLMProvider):
        response = llm.generate(prompt, temperature=0.92, max_tokens=max_tokens, thinking_budget=thinking_budget)
    else:
        from langchain_core.messages import HumanMessage
        resp = llm.invoke([HumanMessage(content=prompt)])
        response = resp.content

    result = parse_llm_json(response)
    if not isinstance(result, list):
        return [{"id": "opening_0", "text": current_opening, "strategy": "mimicry", "slop_flag": False, "slop_penalty": 0}]

    # Always start with the current customized opening as a candidate
    openings = [{
        "id": "opening_0", 
        "text": current_opening, 
        "strategy": "mimicry", 
        "slop_flag": _is_slop(current_opening),
        "slop_penalty": _slop_score_penalty(current_opening)
    }]
    
    slop_count = 1 if openings[0]["slop_flag"] else 0
    for i, item in enumerate(result[:n-1]): # Leave room for the original
        if isinstance(item, dict) and "text" in item:
            item["id"] = item.get("id", f"opening_{i+1}")
            item["slop_flag"] = _is_slop(item["text"])
            item["slop_penalty"] = _slop_score_penalty(item["text"])
            if item["slop_flag"]:
                slop_count += 1
            openings.append(item)

    if not openings:
        openings = [{"id": "opening_0", "text": current_opening, "strategy": "original", "slop_flag": False, "slop_penalty": 0}]

    logger.info("Generated %d opening lines (%d flagged as slop)", len(openings), slop_count)
    for i, o in enumerate(openings):
        slop_marker = " SLOP" if o.get("slop_flag") else ""
        print(
            f"\033[34m[OpeningMassacre]\033[0m   #{i+1} [{o.get('strategy', '?')}]: "
            f"{o['text'][:90]}{'...' if len(o['text']) > 90 else ''}{slop_marker}",
            file=sys.stderr,
            flush=True,
        )
    return openings


# ─────────────────────────────────────────────────────────
# SCORING
# ─────────────────────────────────────────────────────────

def _load_scoring_addon() -> str:
    """Load the agent system prompt addon for opening line scoring."""
    return load_prompt(PROMPTS_DIR / "opening_scoring_agent_addon.txt")


def _build_scoring_prompt(line: dict, post_body: str) -> str:
    """Fill the opening_score_single.txt template for a single opening line."""
    template = load_prompt(PROMPTS_DIR / "opening_score_single.txt")
    return fill_prompt(template, **{
        "opening_text": line["text"],
        "strategy": line.get("strategy", "unknown"),
        "post_body": post_body[:400],
    })


def score_opening_lines_with_audience(
    llm,
    opening_lines: list[dict],
    post_body: str,
    audience_agents: list[dict],
    personality_card: str,
    event_callback=None,
    max_tokens: int = 400,
    thinking_budget: int | None = None,
) -> dict:
    """Score opening lines using audience agents with anti-slop penalties."""
    from ..generation.audience_panel import audience_agent_system_prompt

    # Load the scoring addon once — it's the same for all agents
    scoring_addon = _load_scoring_addon()

    print(
        f"\033[34m[OpeningMassacre]\033[0m \033[1mScoring {len(opening_lines)} openings "
        f"with {len(audience_agents)} agents\033[0m",
        file=sys.stderr,
        flush=True,
    )

    agent_votes: dict[str, dict] = {}

    for agent in audience_agents:
        agent_id = agent["id"]
        agent_votes[agent_id] = {}
        print(f"\033[34m[OpeningMassacre]\033[0m Agent: {agent['name']}", file=sys.stderr, flush=True)

        sys_prompt = audience_agent_system_prompt(agent) + scoring_addon

        for line in opening_lines:
            lid = line["id"]
            scoring_prompt = _build_scoring_prompt(line, post_body)

            from ..llm.base import LLMProvider
            if isinstance(llm, LLMProvider):
                resp_text = llm.generate(
                    scoring_prompt,
                    system_prompt=sys_prompt,
                    temperature=0.3,
                    max_tokens=max_tokens,
                    thinking_budget=thinking_budget,
                )
            else:
                from langchain_core.messages import HumanMessage, SystemMessage
                resp = llm.invoke([
                    SystemMessage(content=sys_prompt),
                    HumanMessage(content=scoring_prompt),
                ])
                resp_text = resp.content

            result = parse_llm_json(resp_text)
            if not isinstance(result, dict):
                result = {"score": 5, "feedback": "Parse error — defaulting.", "subscores": {}, "slop_detected": False}

            raw_score = max(1, min(10, int(result.get("score", 5))))

            slop_penalty = line.get("slop_penalty", 0.0)
            agent_slop_detected = result.get("slop_detected", False)
            if agent_slop_detected:
                slop_penalty = min(slop_penalty, -1.0)

            adjusted_score = max(1, round(raw_score + slop_penalty))

            agent_votes[agent_id][lid] = {
                "raw_score": raw_score,
                "slop_penalty": slop_penalty,
                "score": adjusted_score,
                "subscores": result.get("subscores", {}),
                "feedback": result.get("feedback", ""),
                "slop_detected": agent_slop_detected or line.get("slop_flag", False),
            }

            score_display = f"{adjusted_score}/10"
            if slop_penalty < 0:
                score_display += f" (raw={raw_score}, slop={slop_penalty})"
            print(
                f"\033[34m[OpeningMassacre]\033[0m   {agent['name']} -> {lid}: {score_display}",
                file=sys.stderr,
                flush=True,
            )

        if event_callback:
            event_callback(agent_id, agent["name"], agent_votes[agent_id])

    # ── Aggregate ──
    aggregated = {}
    for line in opening_lines:
        lid = line["id"]
        scores = []
        subscores_agg = {"stop_scroll": [], "specificity": [], "humanness": [], "curiosity": [], "body_fit": []}

        for a in audience_agents:
            vote = agent_votes.get(a["id"], {}).get(lid)
            if vote:
                scores.append(vote["score"])
                for key in subscores_agg:
                    if key in vote.get("subscores", {}):
                        subscores_agg[key].append(vote["subscores"][key])

        mean_score = round(mean(scores), 2) if scores else 0
        mean_subscores = {k: round(mean(v), 2) if v else 0 for k, v in subscores_agg.items()}

        aggregated[lid] = {
            "mean": mean_score,
            "mean_subscores": mean_subscores,
            "scores_by_agent": {
                a["id"]: agent_votes[a["id"]][lid]["score"]
                for a in audience_agents
                if lid in agent_votes.get(a["id"], {})
            },
            "slop_flagged": line.get("slop_flag", False),
            "consensus": max(scores) - min(scores) <= 2 if len(scores) >= 2 else True,
        }

    # ── Winner selection — primary: mean score; tiebreak: humanness subscore ──
    def _sort_key(lid):
        agg = aggregated[lid]
        return (agg["mean"], agg["mean_subscores"].get("humanness", 0))

    winning_id = max(aggregated, key=_sort_key) if aggregated else opening_lines[0]["id"]
    winning_line = next((l for l in opening_lines if l["id"] == winning_id), opening_lines[0])

    sorted_ids = sorted(aggregated, key=_sort_key, reverse=True)
    runner_up_id = sorted_ids[1] if len(sorted_ids) > 1 else winning_id
    runner_up_line = next((l for l in opening_lines if l["id"] == runner_up_id), winning_line)

    print(
        f"\033[34m[OpeningMassacre]\033[0m \033[32m-> WINNER: {winning_id} "
        f"(mean={aggregated.get(winning_id, {}).get('mean', '?')}): "
        f"{winning_line['text'][:90]}\033[0m",
        file=sys.stderr,
        flush=True,
    )
    if runner_up_id != winning_id:
        print(
            f"\033[34m[OpeningMassacre]\033[0m \033[33m-> RUNNER-UP: {runner_up_id} "
            f"(mean={aggregated.get(runner_up_id, {}).get('mean', '?')}): "
            f"{runner_up_line['text'][:90]}\033[0m",
            file=sys.stderr,
            flush=True,
        )

    return {
        "agent_votes": agent_votes,
        "aggregated": aggregated,
        "winning_id": winning_id,
        "winning_line": winning_line,
        "runner_up_id": runner_up_id,
        "runner_up_line": runner_up_line,
    }


def apply_winning_opening(post_text: str, winning_line: dict) -> str:
    """Replace the first paragraph of the post with the winning opening line."""
    paragraphs = post_text.strip().split("\n\n")
    if not paragraphs:
        return winning_line["text"]
    paragraphs[0] = winning_line["text"]
    return "\n\n".join(paragraphs)