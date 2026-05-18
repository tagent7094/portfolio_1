"""v6 pack rejection report writer.

When the validate-regen loop returns `ShipDecision(ship=False)`, OR when
`06_compile.txt` returns `pack_decision: reject`, the orchestrator writes a
structured rejection report instead of an Excel pack.

The JSON shape matches README §"What v6 surfaces to the user on rejection".
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)
_PROJECT_ROOT = Path(__file__).parent.parent.parent


def write_rejection_report(
    state,                         # BatchState
    pack,                          # PackResult (may have partial posts)
    ship_decision,                 # regen_loop.ShipDecision
    compile_decision: dict | None = None,
) -> Path:
    """Write the rejection report to `data/output/<date>/<founder>_<pack#>_REJECTED.json`.

    Returns the written path. Caller is responsible for SSE emission separately.
    """
    today = datetime.utcnow().strftime("%Y-%m-%d")
    out_dir = _PROJECT_ROOT / "data" / "output" / today
    out_dir.mkdir(parents=True, exist_ok=True)

    pack_num = getattr(pack, "source_number", "?") if pack else "?"
    fname = f"{state.founder_slug}_pack_{pack_num}_REJECTED.json"
    out_path = out_dir / fname

    # Aggregate per-post failure details for the report.
    rejected_posts: list[str] = []
    failed_parameters_by_post: dict[str, list[dict]] = {}

    validator_decision = (
        ship_decision.detailed_failures.get("pack_decision", {})
        if ship_decision.detailed_failures else {}
    )
    per_post = ship_decision.detailed_failures.get("per_post_validation", []) if ship_decision.detailed_failures else []

    for entry in per_post:
        if not isinstance(entry, dict):
            continue
        label = entry.get("label", "")
        if not label:
            continue
        if not entry.get("passes_9_7_floor", True):
            rejected_posts.append(label)
            scores = entry.get("scores", {}) or {}
            failures_for_post = []
            for param, score in scores.items():
                try:
                    score_val = float(score)
                except (TypeError, ValueError):
                    continue
                if score_val < 9.7:
                    failures_for_post.append({
                        "parameter": param,
                        "score": score_val,
                        "reason": entry.get("regen_reason", "") or entry.get("violations_detected", ""),
                    })
            failed_parameters_by_post[label] = failures_for_post

    failure_summary = (
        compile_decision.get("failure_summary") if compile_decision
        else ship_decision.rejection_reason or "Pack failed 9.7+ quality floor"
    )
    recommendations = ship_decision.recommendations or (
        compile_decision.get("recommendations", []) if compile_decision else []
    )
    # Normalize: if recommendations entries are dicts (06_compile shape),
    # flatten to strings for the README's shape.
    rec_strings: list[str] = []
    for r in recommendations:
        if isinstance(r, str):
            rec_strings.append(r)
        elif isinstance(r, dict):
            text = r.get("specifics") or r.get("action") or ""
            if text:
                rec_strings.append(text)

    report = {
        "pack_quality_floor_met": False,
        "failure_summary": failure_summary,
        "rejected_posts": rejected_posts,
        "failed_parameters_by_post": failed_parameters_by_post,
        "recommendations": rec_strings,
        "founder_slug": state.founder_slug,
        "pack_number": pack_num,
        "total_regens_used": ship_decision.total_regens_used,
        "validator_pack_decision": validator_decision,
        "regen_log": list(state.regen_log or []),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    if compile_decision:
        report["compile_decision_raw"] = compile_decision

    try:
        out_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("[rejection_report] wrote %s", out_path)
    except Exception as e:
        logger.warning("[rejection_report] failed to write %s: %s", out_path, e)
    return out_path
