"""Post refinement using structured audience feedback.

Enhanced to pass the full rich feedback from the audience panel
(dimension scores, detected patterns, weakest moments, suggested rewrites)
into the refine_post prompt for surgical, targeted revision.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from ..utils.text_utils import load_prompt, fill_prompt

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"


def _format_feedback_summary(audience_feedback: dict[str, dict]) -> str:
    """Format audience feedback into a structured summary for the refiner prompt.

    Organizes feedback by priority: FIX items first, then detail.
    """
    lines = []

    # Collect common themes for a priority header
    all_scores = [fb.get("score", 5) for fb in audience_feedback.values()]
    mean_score = sum(all_scores) / len(all_scores) if all_scores else 5
    lines.append(f"OVERALL: Mean audience score = {mean_score:.1f}/10 across {len(audience_feedback)} readers.\n")

    # Identify weakest dimensions across agents
    dim_totals: dict[str, list[int]] = {}
    for fb in audience_feedback.values():
        for dim, val in fb.get("dimension_scores", {}).items():
            dim_totals.setdefault(dim, []).append(val)

    if dim_totals:
        dim_means = {d: sum(v) / len(v) for d, v in dim_totals.items()}
        weakest = min(dim_means, key=dim_means.get)
        strongest = max(dim_means, key=dim_means.get)
        lines.append(f"WEAKEST DIMENSION: {weakest} ({dim_means[weakest]:.1f}/10)")
        lines.append(f"STRONGEST DIMENSION: {strongest} ({dim_means[strongest]:.1f}/10)\n")

    # Authenticity consensus
    auth_verdicts = [fb.get("authenticity_verdict", "mixed") for fb in audience_feedback.values()]
    if auth_verdicts:
        consensus = max(set(auth_verdicts), key=auth_verdicts.count)
        lines.append(f"AUTHENTICITY CONSENSUS: {consensus}\n")

    # Individual agent feedback
    lines.append("--- INDIVIDUAL READER FEEDBACK ---\n")
    for agent_name, fb in audience_feedback.items():
        score = fb.get("score", "?")
        feedback_text = fb.get("feedback", "No feedback")

        # Build a rich feedback block
        parts = [f"**{agent_name}** (score: {score}/10):"]
        parts.append(f"  Feedback: {feedback_text}")

        # Dimension breakdown if available
        dims = fb.get("dimension_scores", {})
        if dims:
            low_dims = {k: v for k, v in dims.items() if v <= 5}
            if low_dims:
                dim_str = ", ".join(f"{k}={v}" for k, v in sorted(low_dims.items(), key=lambda x: x[1]))
                parts.append(f"  Low dimensions: {dim_str}")

        # Stop scroll signal
        if fb.get("stop_scroll") is False:
            parts.append("  ⚠ Would NOT stop scrolling for this post.")

        lines.append("\n".join(parts))

    return "\n\n".join(lines)


def refine_post_with_feedback(
    llm,
    post: dict,
    audience_feedback: dict[str, dict],
    personality_card: str,
    platform: str = "linkedin",
) -> dict:
    """Rewrite a post incorporating structured audience agent feedback.

    Args:
        llm: LLM provider or LangChain ChatModel
        post: Post dict with 'id', 'text', 'engine_id', 'engine_name'
        audience_feedback: {agent_name: {score, feedback, dimension_scores, ...}}
            This should be the structured output from audience_panel._format_feedback_for_refiner()
        personality_card: Founder personality context
        platform: Target platform

    Returns:
        {id, original_text, refined_text, engine_id, engine_name, feedback_used, refinement_metadata}
    """
    original_len = len(post.get("text", ""))
    n_feedback = len(audience_feedback)

    print(
        f"\033[34m[Refiner]\033[0m \033[1mRefining post {post.get('id', '?')} "
        f"({original_len} chars) with {n_feedback} feedback items\033[0m",
        file=sys.stderr, flush=True,
    )

    template = load_prompt(PROMPTS_DIR / "refine_post.txt")

    # Use the rich formatting
    feedback_summary = _format_feedback_summary(audience_feedback)

    prompt = fill_prompt(
        template,
        platform=platform,
        original_post=post["text"],
        feedback_summary=feedback_summary,
        personality_card=personality_card or "Not available.",
    )

    from ..llm.base import LLMProvider

    if isinstance(llm, LLMProvider):
        refined_text = llm.generate(prompt, temperature=0.7, max_tokens=2000)
    else:
        from langchain_core.messages import HumanMessage
        response = llm.invoke([HumanMessage(content=prompt)])
        refined_text = response.content

    refined = refined_text.strip()
    refined_len = len(refined)

    # Compute change ratio
    change_ratio = abs(refined_len - original_len) / max(original_len, 1)

    # Simple diff detection: how many words changed
    original_words = set(post["text"].lower().split())
    refined_words = set(refined.lower().split())
    words_added = len(refined_words - original_words)
    words_removed = len(original_words - refined_words)
    total_original_words = len(post["text"].split())
    change_pct = round((words_added + words_removed) / max(total_original_words, 1) * 100, 1)

    # Warn if change is too extreme
    if change_pct > 60:
        print(
            f"\033[34m[Refiner]\033[0m \033[33m⚠ High change ratio: {change_pct}% of words changed — "
            f"may have lost voice fidelity\033[0m",
            file=sys.stderr, flush=True,
        )
    elif change_pct < 5:
        print(
            f"\033[34m[Refiner]\033[0m \033[33m⚠ Low change ratio: {change_pct}% — "
            f"refinement may not have addressed feedback\033[0m",
            file=sys.stderr, flush=True,
        )

    print(
        f"\033[34m[Refiner]\033[0m \033[32m→ Original: {original_len} chars → "
        f"Refined: {refined_len} chars (Δ words: +{words_added}/-{words_removed}, "
        f"{change_pct}% changed)\033[0m",
        file=sys.stderr, flush=True,
    )

    return {
        "id": post["id"],
        "original_text": post["text"],
        "refined_text": refined,
        "engine_id": post.get("engine_id", ""),
        "engine_name": post.get("engine_name", ""),
        "feedback_used": audience_feedback,
        "refinement_metadata": {
            "original_chars": original_len,
            "refined_chars": refined_len,
            "change_pct": change_pct,
            "words_added": words_added,
            "words_removed": words_removed,
        },
    }
