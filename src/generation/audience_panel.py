"""Audience sub-agent panel for post scoring and feedback.

Enhanced to extract the full rich output from the audience_score.txt prompt:
- 8 dimension scores
- Pattern detection with penalties
- Behavioral signals (stop_scroll, read_to_end, etc.)
- Authenticity verdicts
- Strongest/weakest moments + actionable rewrites
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from statistics import mean

import yaml

from ..utils.json_parser import parse_llm_json
from ..utils.text_utils import load_prompt, fill_prompt

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_audience_agents(config_path: str | None = None) -> list[dict]:
    """Load audience agent definitions from YAML config."""
    path = Path(config_path) if config_path else CONFIG_DIR / "audience-agents.yaml"
    if not path.exists():
        logger.warning("Audience agents config not found at %s", path)
        return []
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("audience_agents", [])


def audience_agent_system_prompt(agent: dict) -> str:
    """Build a system prompt for an audience sub-agent.

    This is used both by audience_panel and by opening_line_massacre
    for consistent agent behavior.
    """
    return (
        f"You are '{agent['name']}', a specific type of LinkedIn reader.\n\n"
        f"## YOUR IDENTITY\n{agent['description']}\n\n"
        f"## YOUR SCORING BIAS\n{agent['scoring_bias']}\n\n"
        f"## YOUR FEEDBACK FOCUS\n{agent['feedback_focus']}\n\n"
        "You score posts honestly from your perspective. You are NOT a neutral judge — "
        "you have specific biases that should visibly influence your scoring. "
        "Be specific in feedback: reference exact lines, phrases, or moments. "
        "Generic feedback like 'good post' or 'needs improvement' is a failure.\n\n"
        "ANTI-INFLATION: The average LinkedIn post is a 5. A 7 means you'd actually comment. "
        "Most posts don't earn that. Score honestly."
    )


def _score_single_post(llm, agent: dict, post: dict, personality_card: str) -> dict:
    """Score a single post with a single audience agent.

    Returns the FULL rich JSON from the enhanced audience_score prompt,
    not just {score, feedback}.
    """
    template = load_prompt(PROMPTS_DIR / "audience_score.txt")
    prompt = fill_prompt(
        template,
        agent_description=agent["description"],
        scoring_bias=agent["scoring_bias"],
        feedback_focus=agent["feedback_focus"],
        post_text=post["text"],
        personality_card=personality_card or "Not available.",
    )

    sys_prompt = audience_agent_system_prompt(agent)

    from ..llm.base import LLMProvider

    if isinstance(llm, LLMProvider):
        response_text = llm.generate(
            prompt,
            system_prompt=sys_prompt,
            temperature=0.3,
            max_tokens=800,  # Increased for richer output
        )
    else:
        from langchain_core.messages import HumanMessage, SystemMessage
        response = llm.invoke([
            SystemMessage(content=sys_prompt),
            HumanMessage(content=prompt),
        ])
        response_text = response.content

    result = parse_llm_json(response_text)
    if not isinstance(result, dict):
        result = {}

    # Ensure core fields exist with defaults
    result.setdefault("score", 5)
    result["score"] = max(1, min(10, int(result["score"])))
    result.setdefault("feedback", "No feedback provided.")
    result.setdefault("score_before_penalties", result["score"])
    result.setdefault("score_ceiling_hit", None)
    result.setdefault("stop_scroll", False)
    result.setdefault("read_past_line_3", False)
    result.setdefault("read_to_end", False)
    result.setdefault("would_react", False)
    result.setdefault("would_share", False)
    result.setdefault("would_remember_tomorrow", False)
    result.setdefault("detected_patterns", [])
    result.setdefault("dimension_scores", {})
    result.setdefault("strongest_moment", None)
    result.setdefault("weakest_moment", None)
    result.setdefault("missed_opportunity", None)
    result.setdefault("one_line_rewrite", None)
    result.setdefault("authenticity_verdict", "mixed")

    # Tag with agent info for downstream use
    result["agent_id"] = agent["id"]
    result["agent_name"] = agent["name"]

    return result


def _format_feedback_for_refiner(agent_results: dict[str, dict]) -> dict[str, dict]:
    """Format audience feedback into the structure the refiner expects.

    Converts rich audience results into actionable feedback summaries
    that the refine_post prompt can use effectively.
    """
    formatted = {}
    for agent_id, result in agent_results.items():
        agent_name = result.get("agent_name", agent_id)
        feedback_parts = [result.get("feedback", "")]

        # Add the weakest moment if available
        if result.get("weakest_moment"):
            feedback_parts.append(f"Weakest moment: {result['weakest_moment']}")

        # Add the missed opportunity if available
        if result.get("missed_opportunity"):
            feedback_parts.append(f"Missed opportunity: {result['missed_opportunity']}")

        # Add the one-line rewrite if available
        if result.get("one_line_rewrite"):
            feedback_parts.append(f"Suggested rewrite: {result['one_line_rewrite']}")

        # Add pattern flags
        patterns = result.get("detected_patterns", [])
        if patterns:
            pattern_names = [p.get("pattern", "?") for p in patterns if not p.get("subverted", False)]
            if pattern_names:
                feedback_parts.append(f"Detected patterns: {', '.join(pattern_names)}")

        formatted[agent_name] = {
            "score": result.get("score", 5),
            "feedback": " | ".join(filter(None, feedback_parts)),
            "dimension_scores": result.get("dimension_scores", {}),
            "authenticity_verdict": result.get("authenticity_verdict", "mixed"),
            "stop_scroll": result.get("stop_scroll", False),
        }

    return formatted


def score_posts_with_audience(
    llm,
    posts: list[dict],
    audience_agents: list[dict],
    personality_card: str,
    event_callback=None,
) -> dict:
    """Score all posts with all audience agents.

    Returns the full rich output including dimension scores, patterns,
    behavioral signals, and structured feedback for the refiner.
    """
    from .voting import aggregate_audience_scores, pick_top_n

    print(
        f"\033[34m[AudiencePanel]\033[0m \033[1mScoring {len(posts)} posts "
        f"with {len(audience_agents)} audience agents\033[0m",
        file=sys.stderr, flush=True,
    )

    agent_votes: dict[str, dict] = {}  # {agent_id: {post_id: full_result}}

    for agent in audience_agents:
        agent_id = agent["id"]
        agent_votes[agent_id] = {}
        print(
            f"\033[34m[AudiencePanel]\033[0m Agent: {agent['name']} ({agent_id})",
            file=sys.stderr, flush=True,
        )

        for post in posts:
            pid = post["id"]
            print(
                f"\033[34m[AudiencePanel]\033[0m   {agent['name']} scoring {pid}...",
                file=sys.stderr, flush=True,
            )
            result = _score_single_post(llm, agent, post, personality_card)
            agent_votes[agent_id][pid] = result

            # Rich log line
            score = result["score"]
            scroll = "✓" if result.get("stop_scroll") else "✗"
            auth = result.get("authenticity_verdict", "?")[:6]
            patterns = len(result.get("detected_patterns", []))
            print(
                f"\033[34m[AudiencePanel]\033[0m   \033[32m→ score={score}/10 "
                f"scroll={scroll} auth={auth} patterns={patterns}\033[0m",
                file=sys.stderr, flush=True,
            )

        if event_callback:
            event_callback(agent_id, agent["name"], agent_votes[agent_id])

    # ── Aggregate per post ──
    aggregated: dict[str, dict] = {}
    feedback_for_refiner: dict[str, dict] = {}  # {post_id: {agent_name: structured_feedback}}

    for post in posts:
        pid = post["id"]

        # Collect all agent results for this post
        post_results = []
        post_agent_results = {}
        for agent in audience_agents:
            aid = agent["id"]
            if pid in agent_votes.get(aid, {}):
                result = agent_votes[aid][pid]
                post_results.append(result)
                post_agent_results[aid] = result

        # Use the rich aggregation function
        agg = aggregate_audience_scores(post_results)
        aggregated[pid] = agg

        # Format feedback for refiner
        feedback_for_refiner[pid] = _format_feedback_for_refiner(post_agent_results)

    # ── Select top posts ──
    # Build a scores dict compatible with pick_top_n
    scores_for_ranking = {pid: {"mean_score": agg["mean_score"]} for pid, agg in aggregated.items()}
    top_ids = pick_top_n(scores_for_ranking, n=3)

    print(
        f"\033[34m[AudiencePanel]\033[0m \033[32m→ Top posts: {top_ids} "
        f"(means: {[aggregated[pid]['mean_score'] for pid in top_ids]})\033[0m",
        file=sys.stderr, flush=True,
    )

    # Log dimension breakdown for top post
    if top_ids and top_ids[0] in aggregated:
        top_agg = aggregated[top_ids[0]]
        dims = top_agg.get("dimension_means", {})
        if dims:
            dim_str = " | ".join(f"{k}={v}" for k, v in dims.items())
            print(
                f"\033[34m[AudiencePanel]\033[0m   Top post dimensions: {dim_str}",
                file=sys.stderr, flush=True,
            )
        patterns = top_agg.get("patterns_detected", [])
        if patterns:
            pat_str = ", ".join(f"{p['pattern']}(×{p['flagged_by_n_agents']})" for p in patterns[:3])
            print(
                f"\033[34m[AudiencePanel]\033[0m   Patterns detected: {pat_str}",
                file=sys.stderr, flush=True,
            )

    return {
        "agent_votes": agent_votes,
        "aggregated": aggregated,
        "top_ids": top_ids,
        "feedback_for_refiner": feedback_for_refiner,
    }


def select_top_posts(aggregated: dict, n: int = 3) -> list[str]:
    """Select top N post IDs by mean audience score.

    Legacy compat — prefer using pick_top_n from voting.py directly.
    """
    sorted_posts = sorted(
        aggregated.items(),
        key=lambda x: x[1].get("mean_score", x[1].get("mean", 0)),
        reverse=True,
    )
    return [pid for pid, _ in sorted_posts[:n]]
