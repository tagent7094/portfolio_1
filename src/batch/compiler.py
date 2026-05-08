"""Compile batch results into a single JSON output file."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from dataclasses import asdict
from pathlib import Path

from .state import BatchState, PackResult, AmplifiedPost

logger = logging.getLogger(__name__)


def compile_json(state: BatchState) -> dict:
    """Compile all packs into the final output structure."""
    packs_out = []
    total_posts = 0

    for pack in state.packs:
        posts_out = []
        for p in pack.posts:
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
                    "gates": p.gates,
                    "rating": p.rating,
                    "buried_gold": p.buried_gold,
                    "versions_considered": p.versions_considered,
                },
                "events_used": p.events_used,
                "argument_compressed": p.argument_compressed,
            })
            total_posts += 1

        packs_out.append({
            "source_number": pack.source_number,
            "source_post": pack.source_post[:500],
            "source_dissection": pack.dissection,
            "mirrorable": pack.mirrorable,
            "posts": posts_out,
            "batch_a_count": pack.batch_a_count,
            "batch_b_count": pack.batch_b_count,
            "convergence_test": pack.convergence_test,
        })

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
        },
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
        },
    }

    if state.tracer:
        output["traceability"] = {
            "summary": state.tracer.get_summary(),
            "traces": state.tracer.to_list(),
        }

    if state.web_search_context:
        output["web_search"] = {
            "trending_topics": state.web_search_context.get("trending_topics", []),
            "facts": state.web_search_context.get("facts", []),
            "contrarian_angles": state.web_search_context.get("contrarian_angles", []),
            "searches_performed": state.web_search_context.get("searches", []),
        }

    return output


def save_output(output: dict, state: BatchState) -> str:
    """Save compiled JSON to the founder's post-data directory."""
    import yaml

    config_path = Path(__file__).parent.parent.parent / "config" / "llm-config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    from ..config.founders import get_founder_paths
    paths = get_founder_paths(config, state.founder_slug)

    data_dir = Path(paths["data_dir"]).parent
    post_data_dir = data_dir / "post-data"
    post_data_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    filename = f"{state.founder_slug}_batch_{date_str}.json"
    filepath = post_data_dir / filename

    counter = 1
    while filepath.exists():
        filename = f"{state.founder_slug}_batch_{date_str}_{counter}.json"
        filepath = post_data_dir / filename
        counter += 1

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    logger.info("[batch] Saved output to %s (%d posts)", filepath, output["metadata"]["total_posts"])
    return str(filepath)
