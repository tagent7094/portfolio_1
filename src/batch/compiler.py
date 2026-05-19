"""Compile batch results into JSON output files (posts + logs)."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from .state import BatchState
from .tracer import BatchTracer

logger = logging.getLogger(__name__)


_PROMPTS_DIR = Path(__file__).parent / "prompts"
_VERSION_RE = re.compile(r"^#\s*version:\s*([vV][\d.]+)\s*$", re.MULTILINE)


def _read_prompt_versions() -> dict[str, str]:
    """Scan prompts/*.txt for `# version: vX.Y.Z` headers and return a dict
    keyed by prompt name (without extension). Used to emit per-prompt versions
    into pack metadata so the operator can see exactly which prompts ran."""
    versions: dict[str, str] = {}
    if not _PROMPTS_DIR.exists():
        return versions
    for path in _PROMPTS_DIR.glob("*.txt"):
        if "backup" in path.name:
            continue
        try:
            head = path.read_text(encoding="utf-8")[:512]
            m = _VERSION_RE.search(head)
            versions[path.stem] = m.group(1) if m else "unstamped"
        except Exception:
            versions[path.stem] = "unreadable"
    return versions


def compile_json(state: BatchState) -> dict:
    """Compile all packs into the final output structure (posts + metadata, no logs)."""
    packs_out = []
    total_posts = 0

    for pack in state.packs:
        posts_out = []
        for p in pack.posts:
            variants_out = []
            for v in (p.opener_variants or []):
                variants_out.append({
                    "variant": v.get("variant", ""),
                    "opening": v.get("opening", ""),
                    "mechanic": v.get("mechanic", ""),
                    "key_change": v.get("key_change", ""),
                    "expected_lift": v.get("expected_lift", ""),
                    "rating": v.get("rating", 0),
                })

            # Batch A bypass safety net: if the session bypass set voice_score=3
            # and something downstream reset it to 0, re-stamp from the
            # validation_result.overall="SKIP" signal. Also surface dimension
            # breakdown so operators can diagnose low scores at a glance.
            vr = p.validation_result or {}
            vs = p.voice_score
            if p.batch == "A" and vr.get("overall") == "SKIP" and vs == 0:
                logger.warning(
                    "[compiler] %s: Batch A voice_score=0 despite SKIP bypass — restamping to 3",
                    p.label,
                )
                vs = 3
                p.voice_score = 3

            # v6.1: pull per-post validator scores from the dict the
            # pack-level validator stamps onto post.validation_result.
            scores = getattr(p, "validator_scores", None) or vr.get("scores", {}) or {}

            posts_out.append({
                "label": p.label,
                "batch": p.batch,
                "entry_door": p.entry_door,
                "mode": p.mode,
                "text": p.text,
                "word_count": p.word_count,
                # Top-level transpose-set fields (no longer hidden under amplifier).
                "mechanic": p.mechanic,
                "closer_mechanic": p.closer_mechanic,
                "anchor_consumed_id": p.anchor_consumed_id,
                "authority_anchor": p.authority_anchor,
                "body_format": p.body_format,
                "stories_used": p.stories_used,
                "amplifier": {
                    "original_opening": p.original_opening,
                    "final_opening": p.final_opening,
                    "mechanic": p.mechanic,
                    "actual_mechanic": p.actual_mechanic,
                    "gates": p.gates,
                    "rating": p.rating,
                    "buried_gold": p.buried_gold,
                    "weakness": p.weakness,
                    "versions_considered": p.versions_considered,
                    "recommended_variant": p.recommended_variant,
                    "variants": variants_out,
                },
                "voice_validation": {
                    "voice_score": vs,
                    "voice_marker_score": (
                        scores.get("voice_marker")
                        if scores else vr.get("voice_marker_score")
                    ),
                    "register_score": (
                        scores.get("register")
                        if scores else vr.get("register_score")
                    ),
                    "posture_score": (
                        scores.get("posture")
                        if scores else vr.get("posture_score")
                    ),
                    "opener_rhythm_score": (
                        scores.get("opener_rhythm")
                        if scores else vr.get("opener_rhythm_score")
                    ),
                    "formatting_score": (
                        scores.get("formatting")
                        if scores else vr.get("formatting_score")
                    ),
                    "anchor_grounding_score": scores.get("anchor_grounding"),
                    "first_degree_truth_score": scores.get("first_degree_truth"),
                    "overall": vr.get("overall"),
                    "register_reads_as": vr.get("register_reads_as"),
                    "posture_reads_as": vr.get("posture_reads_as"),
                    "passes_9_7_floor": bool(getattr(p, "passes_9_7_floor", False)),
                    # v6.1 sub-mechanic enforcement
                    "required_sub_mechanic": getattr(p, "required_sub_mechanic", ""),
                    "actual_sub_mechanic_used": getattr(p, "actual_sub_mechanic_used", ""),
                    "sub_mechanic_match": bool(getattr(p, "sub_mechanic_match", False)),
                    "parameter_1_hard_veto_triggered": bool(
                        getattr(p, "parameter_1_hard_veto_triggered", False)
                    ),
                    "result": vr,
                },
                # v6.1: full generator self-assessment + validator detail surfaced
                # for downstream analysis/audit.
                "pre_commit": p.pre_commit or {},
                "self_scores": p.self_scores or {},
                "validator_scores": scores,
                "regen_history": getattr(p, "regen_history", []) or [],
                "surprise_quotient": getattr(p, "surprise_quotient", {}) or {},
                "violations": p.violations,
                "events_used": p.events_used,
                "argument_compressed": p.argument_compressed,
                "saturation_warning": p.saturation_warning,
                "quality_flags": p.quality_flags,
                "regen_count": p.regen_count,
            })
            total_posts += 1

        packs_out.append({
            "source_number": pack.source_number,
            "source_post": pack.source_post,
            "source_dissection": pack.dissection,
            "mirrorable": pack.mirrorable,
            "posts": posts_out,
            "batch_a_count": pack.batch_a_count,
            "batch_b_count": pack.batch_b_count,
            "convergence_test": pack.convergence_test,
            "convergence_warning": pack.convergence_warning,
            "convergence_retry_attempted": pack.convergence_retry_attempted,
            "total_regens": pack.total_regens,
        })

    raw_data = state.raw_data or {}

    # Cost telemetry — what this run cost in USD, broken down by task/model/pack.
    total_cost = round(getattr(state, "total_cost_usd", 0.0), 4)
    cost_block = {
        "total_usd": total_cost,
        "total_input_tokens": getattr(state, "total_input_tokens", 0),
        "total_output_tokens": getattr(state, "total_output_tokens", 0),
        "by_task": {k: round(v, 4) for k, v in getattr(state, "cost_by_task", {}).items()},
        "by_model": {k: round(v, 4) for k, v in getattr(state, "cost_by_model", {}).items()},
        "by_pack": {str(k): round(v, 4) for k, v in getattr(state, "cost_by_pack", {}).items()},
        "warning": None,
    }
    if total_cost > 5.0:
        cost_block["warning"] = f"Spend ${total_cost:.2f} exceeded $5/founder threshold"
        logger.warning(
            "[batch] COST WARNING: $%.2f exceeded $5.00 threshold for founder %s",
            total_cost, state.founder_slug,
        )

    output = {
        "metadata": {
            "founder": state.founder_slug,
            "platform": state.platform,
            "generated_at": datetime.utcnow().isoformat(),
            "total_posts": total_posts,
            "sources_count": len(state.packs),
            "creativity": state.creativity,
            "word_count_range": list(state.word_count_range),
            "median_word_count": state.median_word_count,
            "voice_markers": state.voice_markers,
            "layout": "v6",
            "prompt_version": _read_prompt_versions(),
            "quality_floor": 9.7,
            "rejection_enforcement": True,
            "founder_data_layout": raw_data.get("layout", "unknown"),
            "files_ingested_count": len(raw_data.get("files_ingested", [])),
            "files_skipped_count": len(raw_data.get("files_skipped", [])),
            "files_skipped": raw_data.get("files_skipped", []),
        },
        "cost": cost_block,
        "founder_internalization": state.founder_internalization,
        "packs": packs_out,
        "global_tracking": {
            "total_events_used": len(state.events_used_global),
            "total_unique_arguments": len(state.arguments_compressed),
            "events_list": sorted(state.events_used_global)[:100],
            "convergence_flags": [
                p.convergence_test.get("recommendation", "")
                for p in state.packs
                if not p.convergence_test.get("passed", True)
            ],
            "convergence_warnings": [
                {
                    "source_number": p.source_number,
                    "recommendation": p.convergence_test.get("recommendation", ""),
                    "overlapping_posts": p.convergence_test.get("overlapping_posts", []),
                }
                for p in state.packs
                if p.convergence_warning
            ],
        },
    }

    if state.web_search_context:
        output["web_search"] = {
            "trending_topics": state.web_search_context.get("trending_topics", []),
            "facts": state.web_search_context.get("facts", []),
            "contrarian_angles": state.web_search_context.get("contrarian_angles", []),
            "searches_performed": state.web_search_context.get("searches", []),
        }

    return output


def _next_stem(directory: Path, base: str) -> str:
    """Return the next available stem that's free across .json AND .xlsx AND _log.json.

    Avoids the old bug where the JSON, Excel, and log files could drift onto
    different counter suffixes when one extension's slot was already taken.
    Returns the bare stem (no extension) — caller appends the right extension.
    """
    directory.mkdir(parents=True, exist_ok=True)
    counter = 0
    while True:
        stem = base if counter == 0 else f"{base}_{counter}"
        json_path = directory / f"{stem}.json"
        xlsx_path = directory / f"{stem}.xlsx"
        log_path = directory / f"{stem}_log.json"
        if not json_path.exists() and not xlsx_path.exists() and not log_path.exists():
            return stem
        counter += 1


def save_output(output: dict, state: BatchState) -> str:
    """Save posts JSON + Excel + log JSON, all keyed to the same stem."""
    from ..config.founders import get_post_data_dir

    post_data_dir = get_post_data_dir(state.founder_slug, create=True)
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    base = f"{state.founder_slug}_batch_{date_str}"
    stem = _next_stem(post_data_dir, base)

    json_path = post_data_dir / f"{stem}.json"
    xlsx_path = post_data_dir / f"{stem}.xlsx"
    log_path = post_data_dir / f"{stem}_log.json"

    # 1. JSON first — Excel reads from it.
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    logger.info(
        "[batch] Saved output to %s (%d posts)",
        json_path, output["metadata"]["total_posts"],
    )

    # 2. Excel — keyed to the same stem so the trio stays aligned.
    try:
        from .json_to_excel import convert
        convert(str(json_path), output_path=str(xlsx_path))
        logger.info("[batch] Saved Excel to %s", xlsx_path)
    except Exception as e:
        logger.error("[batch] Failed to generate Excel: %s", e)

    # 3. Log JSON — same stem.
    if state.tracer:
        state.tracer.stop_log_capture()
        log_data = state.tracer.get_debug_log()
        try:
            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False, default=str)
            logger.info("[batch] Saved log to %s", log_path)
        except Exception as e:
            logger.error("[batch] Failed to save log: %s", e)

    # 4. Record used source posts.
    try:
        from .source_tracker import record_used_sources
        source_texts = [pack.source_post for pack in state.packs if pack.source_post]
        record_used_sources(state.founder_slug, source_texts, json_path.name)
    except Exception as e:
        logger.warning("[batch] Failed to record used sources: %s", e)

    # 5. Auto-commit on VPS.
    _auto_git_if_vps(json_path)

    return str(json_path)


def _auto_git_if_vps(filepath: Path):
    """On the VPS (/opt/tagent), auto-commit batch output to git."""
    if not Path("/opt/tagent").exists():
        return
    import subprocess
    try:
        cwd = "/opt/tagent"
        subprocess.run(["git", "add", str(filepath)], cwd=cwd, check=True, timeout=10)
        xlsx = str(filepath).replace(".json", ".xlsx")
        subprocess.run(["git", "add", xlsx], cwd=cwd, check=False, timeout=10)
        log_pattern = str(filepath).replace(".json", "_log.json")
        subprocess.run(["git", "add", log_pattern], cwd=cwd, check=False, timeout=10)
        subprocess.run(
            ["git", "commit", "-m", f"auto: batch output {filepath.name}"],
            cwd=cwd, check=True, timeout=30,
        )
        logger.info("[batch] Auto-committed %s on VPS", filepath.name)
    except Exception as e:
        logger.warning("[batch] Auto-git failed (non-fatal): %s", e)
