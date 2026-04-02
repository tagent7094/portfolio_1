"""Scoring, voting, and aggregation logic for narratives and posts.

Handles the enhanced scoring dimensions from the upgraded prompt suite:
- Narrative scores: safety, traction, alignment, freshness, groundedness
- Post scores: voice_fidelity, hook_strength, argument_quality, engagement_prediction, ai_slop_detection
- Audience scores: 8 dimension scores + pattern penalties + ceiling system
"""

from __future__ import annotations

from statistics import mean, stdev


# ─────────────────────────────────────────────────────────
# NARRATIVE SCORING
# ─────────────────────────────────────────────────────────

NARRATIVE_WEIGHTS = {
    "safety": 0.15,
    "traction": 0.25,
    "alignment": 0.25,
    "freshness": 0.20,
    "groundedness": 0.15,
}

NARRATIVE_DIMENSIONS = list(NARRATIVE_WEIGHTS.keys())


def aggregate_narrative_scores(agent_scores: list[dict]) -> dict:
    """Aggregate narrative scores from multiple agents with weighted composite.

    Handles both old-format (4 dims) and new-format (5 dims with groundedness).
    """
    if not agent_scores:
        return {d: 0 for d in NARRATIVE_DIMENSIONS} | {"composite": 0, "verdict_counts": {}, "consensus": False}

    # Compute mean for each dimension
    dim_means = {}
    dim_stdevs = {}
    for dim in NARRATIVE_DIMENSIONS:
        values = [s.get(dim, 5) for s in agent_scores if isinstance(s.get(dim), (int, float))]
        dim_means[dim] = round(mean(values), 2) if values else 5.0
        dim_stdevs[dim] = round(stdev(values), 2) if len(values) > 1 else 0.0

    # Weighted composite
    composite = sum(dim_means[d] * NARRATIVE_WEIGHTS[d] for d in NARRATIVE_DIMENSIONS)

    # Count verdicts
    verdict_counts: dict[str, int] = {}
    for s in agent_scores:
        v = s.get("verdict", "unknown")
        verdict_counts[v] = verdict_counts.get(v, 0) + 1

    # Consensus: all agents within 2 points on composite
    agent_composites = []
    for s in agent_scores:
        ac = sum(s.get(d, 5) * NARRATIVE_WEIGHTS[d] for d in NARRATIVE_DIMENSIONS)
        agent_composites.append(ac)
    consensus = (max(agent_composites) - min(agent_composites)) <= 2.0 if len(agent_composites) >= 2 else True

    # Interaction flags from agents
    interaction_flags = [s.get("interaction_flag") for s in agent_scores if s.get("interaction_flag")]

    # Upgrade paths from agents (for needs_work verdicts)
    upgrade_paths = [s.get("upgrade_path") for s in agent_scores if s.get("upgrade_path")]

    # Min dimension (for threshold checks)
    min_dim = min(NARRATIVE_DIMENSIONS, key=lambda d: dim_means[d])
    min_dim_value = dim_means[min_dim]

    # Determine aggregate verdict based on thresholds from the enhanced prompt
    if composite >= 7.5 and min_dim_value >= 5 and dim_means.get("groundedness", 5) >= 6:
        agg_verdict = "strong_publish"
    elif composite >= 6.0 and dim_means.get("safety", 5) >= 5 and dim_means.get("groundedness", 5) >= 5:
        agg_verdict = "publish"
    elif composite >= 4.5 or min_dim_value < 4:
        agg_verdict = "needs_work"
    else:
        agg_verdict = "kill"

    return {
        **dim_means,
        "dimension_stdevs": dim_stdevs,
        "composite": round(composite, 2),
        "verdict": agg_verdict,
        "verdict_counts": verdict_counts,
        "consensus": consensus,
        "weakest_dimension": min_dim,
        "weakest_value": min_dim_value,
        "interaction_flags": interaction_flags,
        "upgrade_paths": upgrade_paths,
        # Legacy compat
        "total": round(composite * 4, 2),
    }


# ─────────────────────────────────────────────────────────
# POST SCORING (internal agent scoring via score_post.txt)
# ─────────────────────────────────────────────────────────

POST_WEIGHTS = {
    "voice_fidelity": 0.25,
    "hook_strength": 0.20,
    "argument_quality": 0.20,
    "engagement_prediction": 0.15,
    "ai_slop_detection": 0.20,
}

POST_DIMENSIONS = list(POST_WEIGHTS.keys())


def aggregate_post_scores(agent_scores: list[dict]) -> dict:
    """Aggregate post scores from multiple agents with weighted composite.

    Handles both old-format (4 dims) and new-format (5 dims with ai_slop_detection).
    """
    if not agent_scores:
        return {d: 0 for d in POST_DIMENSIONS} | {"composite": 0, "publish_ready": False}

    dim_means = {}
    for dim in POST_DIMENSIONS:
        values = [s.get(dim, 5) for s in agent_scores if isinstance(s.get(dim), (int, float))]
        dim_means[dim] = round(mean(values), 2) if values else 5.0

    composite = sum(dim_means[d] * POST_WEIGHTS[d] for d in POST_DIMENSIONS)

    # Aggregate slop flags from all agents
    all_slop_flags = []
    for s in agent_scores:
        all_slop_flags.extend(s.get("ai_slop_flags", []))
    # Deduplicate
    unique_slop_flags = list(set(all_slop_flags))

    # Aggregate voice breaks
    all_voice_breaks = []
    for s in agent_scores:
        all_voice_breaks.extend(s.get("voice_breaks", []))
    unique_voice_breaks = list(set(all_voice_breaks))

    # Collect one_line_fix suggestions
    fixes = [s.get("one_line_fix", "") for s in agent_scores if s.get("one_line_fix")]

    # Weakest dimension
    min_dim = min(POST_DIMENSIONS, key=lambda d: dim_means[d])
    min_dim_value = dim_means[min_dim]

    # Strongest dimension
    max_dim = max(POST_DIMENSIONS, key=lambda d: dim_means[d])

    # Publish readiness
    publish_ready = (
        composite >= 7.5
        and min_dim_value >= 5
        and dim_means.get("ai_slop_detection", 5) >= 7
    )

    # Revision priority: the dimension most agents flagged as weakest
    revision_priorities = [s.get("weakest_dimension", "") for s in agent_scores if s.get("weakest_dimension")]
    if revision_priorities:
        revision_priority = max(set(revision_priorities), key=revision_priorities.count)
    else:
        revision_priority = min_dim

    return {
        **dim_means,
        "composite": round(composite, 2),
        "publish_ready": publish_ready,
        "weakest_dimension": min_dim,
        "strongest_dimension": max_dim,
        "ai_slop_flags": unique_slop_flags,
        "voice_breaks": unique_voice_breaks,
        "suggested_fixes": fixes,
        "revision_priority": revision_priority,
        # Legacy compat
        "total": round(composite * 4, 2),
    }


# ─────────────────────────────────────────────────────────
# AUDIENCE SCORING (audience_panel via audience_score.txt)
# ─────────────────────────────────────────────────────────

AUDIENCE_DIMENSIONS = [
    "relevance", "originality", "specificity", "voice_authenticity",
    "structural_craft", "emotional_resonance", "information_density", "shareability",
]


def aggregate_audience_scores(agent_results: list[dict]) -> dict:
    """Aggregate rich audience panel scores from the enhanced audience_score prompt.

    Each agent_result is the full JSON output from audience_score.txt:
    {score, score_before_penalties, dimension_scores, detected_patterns, ...}
    """
    if not agent_results:
        return {"mean_score": 0, "dimension_means": {}, "patterns_detected": [], "consensus": False}

    # Final scores (after penalties + ceiling)
    final_scores = [r.get("score", 5) for r in agent_results if isinstance(r.get("score"), (int, float))]
    pre_penalty_scores = [r.get("score_before_penalties", r.get("score", 5)) for r in agent_results]

    # Dimension-level aggregation
    dim_means = {}
    for dim in AUDIENCE_DIMENSIONS:
        values = []
        for r in agent_results:
            ds = r.get("dimension_scores", {})
            if dim in ds and isinstance(ds[dim], (int, float)):
                values.append(ds[dim])
        dim_means[dim] = round(mean(values), 2) if values else 5.0

    # Pattern detection aggregation (which patterns were flagged by multiple agents)
    pattern_counts: dict[str, int] = {}
    pattern_evidence: dict[str, list[str]] = {}
    total_penalty = 0.0
    for r in agent_results:
        for p in r.get("detected_patterns", []):
            pname = p.get("pattern", "unknown")
            pattern_counts[pname] = pattern_counts.get(pname, 0) + 1
            if p.get("evidence"):
                pattern_evidence.setdefault(pname, []).append(p["evidence"])
            if not p.get("subverted", False):
                total_penalty += p.get("penalty", 0)

    patterns_detected = [
        {
            "pattern": pname,
            "flagged_by_n_agents": count,
            "evidence_samples": pattern_evidence.get(pname, [])[:2],
        }
        for pname, count in sorted(pattern_counts.items(), key=lambda x: -x[1])
    ]

    # Behavioral signals (stop_scroll, read_to_end, etc.)
    behavioral = {}
    for signal in ["stop_scroll", "read_past_line_3", "read_to_end", "would_react", "would_share", "would_remember_tomorrow"]:
        yeses = sum(1 for r in agent_results if r.get(signal) is True)
        behavioral[signal] = round(yeses / len(agent_results), 2) if agent_results else 0

    # Ceiling hits
    ceiling_hits = [r.get("score_ceiling_hit") for r in agent_results if r.get("score_ceiling_hit")]

    # Authenticity verdicts
    auth_verdicts = [r.get("authenticity_verdict", "mixed") for r in agent_results]
    auth_consensus = max(set(auth_verdicts), key=auth_verdicts.count) if auth_verdicts else "mixed"

    # Strongest / weakest moments
    strongest = [r.get("strongest_moment") for r in agent_results if r.get("strongest_moment")]
    weakest = [r.get("weakest_moment") for r in agent_results if r.get("weakest_moment")]
    missed_opps = [r.get("missed_opportunity") for r in agent_results if r.get("missed_opportunity")]
    rewrites = [r.get("one_line_rewrite") for r in agent_results if r.get("one_line_rewrite")]

    # Consensus
    consensus = (max(final_scores) - min(final_scores)) <= 2 if len(final_scores) >= 2 else True

    return {
        "mean_score": round(mean(final_scores), 2) if final_scores else 0,
        "mean_score_before_penalties": round(mean(pre_penalty_scores), 2) if pre_penalty_scores else 0,
        "total_pattern_penalty": round(total_penalty / len(agent_results), 2) if agent_results else 0,
        "dimension_means": dim_means,
        "weakest_dimension": min(dim_means, key=dim_means.get) if dim_means else None,
        "strongest_dimension": max(dim_means, key=dim_means.get) if dim_means else None,
        "patterns_detected": patterns_detected,
        "behavioral_signals": behavioral,
        "ceiling_hits": ceiling_hits,
        "authenticity_verdict": auth_consensus,
        "consensus": consensus,
        "strongest_moments": strongest[:3],
        "weakest_moments": weakest[:3],
        "missed_opportunities": missed_opps[:3],
        "suggested_rewrites": rewrites[:3],
    }


# ─────────────────────────────────────────────────────────
# WINNER SELECTION
# ─────────────────────────────────────────────────────────

def pick_winner(scores: dict[str, dict], prefer_human: bool = True) -> str:
    """Pick the entry with the highest composite score.

    If prefer_human is True (default), uses ai_slop_detection or voice_authenticity
    as a tiebreaker — preferring the more human-sounding option.
    """
    if not scores:
        return ""

    def _sort_key(entry_id: str) -> tuple:
        s = scores[entry_id]
        primary = s.get("composite", s.get("total", s.get("mean_score", s.get("mean", 0))))

        # Tiebreaker: human-sounding-ness
        if prefer_human:
            humanness = s.get("ai_slop_detection", s.get("voice_fidelity", s.get("voice_authenticity", 0)))
        else:
            humanness = 0

        return (primary, humanness)

    return max(scores, key=_sort_key)


def pick_top_n(scores: dict[str, dict], n: int = 3, prefer_human: bool = True) -> list[str]:
    """Pick the top N entries sorted by composite score."""
    if not scores:
        return []

    def _sort_key(entry_id: str) -> tuple:
        s = scores[entry_id]
        primary = s.get("composite", s.get("total", s.get("mean_score", s.get("mean", 0))))
        if prefer_human:
            humanness = s.get("ai_slop_detection", s.get("voice_fidelity", 0))
        else:
            humanness = 0
        return (primary, humanness)

    sorted_ids = sorted(scores, key=_sort_key, reverse=True)
    return sorted_ids[:n]
