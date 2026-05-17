"""Root cause classification for failing audit parameters across iterations.

Looks at the trajectory of a parameter's score over iterations to decide
whether the prompt instruction is missing, unclear, or whether the failure
points to a deeper limitation (founder data, framework).
"""

from __future__ import annotations

import logging
from collections import Counter

logger = logging.getLogger(__name__)


def diagnose_failures(
    current_audit: dict,
    history: list[dict],
    tweaks_applied: set[str],
) -> list[dict]:
    """For each failing parameter in the current audit, return a diagnosis.

    Returns list of {"param": str, "root_cause": str, "fix_location": str,
                     "current_score": int, "trajectory": [int, ...]}
    """
    diagnoses: list[dict] = []
    failing_params = _collect_failing_params(current_audit)

    for param in failing_params:
        trajectory = [_avg_param_score(it["audit"], param) for it in history]
        if current_audit:
            trajectory.append(_avg_param_score(current_audit, param))

        root_cause = _classify(param, trajectory, tweaks_applied)
        fix_location = "transpose.txt" if param != "P8" else "amplifier.py (handled)"
        diagnoses.append({
            "param": param,
            "root_cause": root_cause,
            "fix_location": fix_location,
            "current_score": trajectory[-1] if trajectory else 0,
            "trajectory": trajectory,
        })
    return diagnoses


def _collect_failing_params(audit: dict) -> list[str]:
    """Return list of param IDs failing in at least one post of the pack."""
    failing: set[str] = set()
    for post_audit in audit.get("per_post", []):
        for k in post_audit.get("failing", []):
            failing.add(k)
    return sorted(failing)


def _avg_param_score(audit: dict, param: str) -> float:
    posts = audit.get("per_post", [])
    if not posts:
        return 0.0
    scores = [p.get(param, {}).get("score", 0) for p in posts]
    return sum(scores) / len(scores)


def _classify(param: str, trajectory: list[float], tweaks_applied: set[str]) -> str:
    """Return a one-phrase root cause label."""
    if not trajectory:
        return "no_data"

    last = trajectory[-1]
    if last >= 9:
        return "now_passing"

    if param == "P8":
        return "amplifier_logic_bug_check_recent_amplifier_changes"

    if len(trajectory) >= 2:
        delta = trajectory[-1] - trajectory[-2]
        if abs(delta) > 3:
            return "prompt_instruction_unclear_high_variance"
        if delta < 0 and param in tweaks_applied:
            return "tweak_regressed_consider_revert"
        if abs(delta) < 0.5 and last < 7 and param in tweaks_applied:
            return "tweak_applied_but_no_improvement_founder_data_or_framework_limit"

    if param not in tweaks_applied:
        return "prompt_instruction_missing_apply_tweak"

    return "persistent_failure_under_investigation"


def find_worst_unfixed_parameter(
    audit: dict,
    tweaks_applied: set[str],
) -> str | None:
    """Pick the parameter to tweak next: lowest avg score across posts,
    excluding params already tweaked this run and P8 (handled in amplifier).
    """
    failing = _collect_failing_params(audit)
    if not failing:
        return None

    candidates: list[tuple[str, float]] = []
    for p in failing:
        if p == "P8":
            continue
        if p in tweaks_applied:
            continue
        avg = _avg_param_score(audit, p)
        candidates.append((p, avg))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[1])
    return candidates[0][0]
