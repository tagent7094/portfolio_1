"""Compile batch results into JSON output files (posts + logs)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from .state import BatchState
from .tracer import BatchTracer

logger = logging.getLogger(__name__)


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

            posts_out.append({
                "label": p.label,
                "batch": p.batch,
                "entry_door": p.entry_door,
                "mode": p.mode,
                "text": p.text,
                "word_count": p.word_count,
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
                    "voice_marker_score": vr.get("voice_marker_score"),
                    "register_score": vr.get("register_score"),
                    "posture_score": vr.get("posture_score"),
                    "opener_rhythm_score": vr.get("opener_rhythm_score"),
                    "formatting_score": vr.get("formatting_score"),
                    "overall": vr.get("overall"),
                    "register_reads_as": vr.get("register_reads_as"),
                    "posture_reads_as": vr.get("posture_reads_as"),
                    "result": vr,
                },
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
            "layout": raw_data.get("layout", "unknown"),
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


def _get_output_dir(state: BatchState) -> Path:
    """Resolve the post-data output directory for a founder."""
    import yaml
    config_path = Path(__file__).parent.parent.parent / "config" / "llm-config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    from ..config.founders import get_founder_paths
    paths = get_founder_paths(config, state.founder_slug)
    data_dir = Path(paths["data_dir"]).parent
    post_data_dir = data_dir / "post-data"
    post_data_dir.mkdir(parents=True, exist_ok=True)
    return post_data_dir


def _next_filepath(directory: Path, base: str, ext: str) -> Path:
    """Find next available filename with counter suffix."""
    filepath = directory / f"{base}{ext}"
    counter = 1
    while filepath.exists():
        filepath = directory / f"{base}_{counter}{ext}"
        counter += 1
    return filepath


def save_output(output: dict, state: BatchState) -> str:
    """Save posts JSON + log JSON + Excel to the founder's post-data directory."""
    post_data_dir = _get_output_dir(state)
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    base = f"{state.founder_slug}_batch_{date_str}"

    # 1. Save posts JSON
    filepath = _next_filepath(post_data_dir, base, ".json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    logger.info("[batch] Saved output to %s (%d posts)", filepath, output["metadata"]["total_posts"])

    # 2. Save log JSON (full traces + pipeline logs)
    if state.tracer:
        state.tracer.stop_log_capture()
        log_data = state.tracer.get_debug_log()
        log_path = _next_filepath(post_data_dir, f"{base}_log", ".json")
        try:
            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False, default=str)
            logger.info("[batch] Saved log to %s", log_path)
        except Exception as e:
            logger.error("[batch] Failed to save log: %s", e)

    # 3. Generate Excel from posts JSON
    try:
        from .json_to_excel import convert
        xlsx_path = convert(str(filepath))
        logger.info("[batch] Saved Excel to %s", xlsx_path)
    except Exception as e:
        logger.error("[batch] Failed to generate Excel: %s", e)

    # 4. Record used source posts
    try:
        from .source_tracker import record_used_sources
        source_texts = [pack.source_post for pack in state.packs if pack.source_post]
        record_used_sources(state.founder_slug, source_texts, filepath.name)
    except Exception as e:
        logger.warning("[batch] Failed to record used sources: %s", e)

    # 5. Auto-commit on VPS
    _auto_git_if_vps(filepath)

    return str(filepath)


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
