"""Node coverage tracking — records which graph nodes influence each post."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent


def _fuzzy_present(text: str, reference: str, threshold: float = 0.4) -> float:
    """Check if reference content is reflected in text. Returns similarity score."""
    from difflib import SequenceMatcher
    if not text or not reference:
        return 0.0
    text_lower = text.lower()
    ref_lower = reference.lower()[:200]
    # Quick keyword check first
    ref_words = set(w for w in ref_lower.split() if len(w) > 3)
    text_words = set(text_lower.split())
    if not ref_words:
        return 0.0
    overlap = len(ref_words & text_words) / len(ref_words)
    if overlap > threshold:
        return overlap
    return SequenceMatcher(None, text_lower[:500], ref_lower).ratio()


def track_node_usage(
    post: str,
    graph: nx.DiGraph,
    topic: str,
    platform: str,
    founder_slug: str,
) -> dict:
    """Track which graph nodes influenced a generated post.

    Appends to data/founders/{slug}/node-usage.json.
    Returns matched nodes and coverage stats.
    """
    matched_nodes = []

    for nid, data in graph.nodes(data=True):
        ntype = data.get("node_type", "")
        if ntype in ("founder", "category"):
            continue

        # Build reference text based on node type
        ref = ""
        if ntype == "belief":
            ref = data.get("stance", "")
        elif ntype == "story":
            ref = f"{data.get('title', '')} {data.get('summary', '')}"
        elif ntype == "style_rule":
            ref = data.get("description", "")
        elif ntype == "thinking_model":
            ref = f"{data.get('name', '')} {data.get('description', '')}"
        elif ntype == "contrast_pair":
            ref = data.get("description", "")

        if not ref:
            continue

        score = _fuzzy_present(post, ref)
        if score >= 0.4:
            matched_nodes.append({
                "node_id": nid,
                "node_type": ntype,
                "label": data.get("label", data.get("title", data.get("name", nid))),
                "similarity": round(score, 3),
            })

    # Build usage record
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "topic": topic,
        "platform": platform,
        "post_length": len(post),
        "matched_nodes": [m["node_id"] for m in matched_nodes],
        "match_count": len(matched_nodes),
    }

    # Append to usage file
    usage_path = PROJECT_ROOT / "data" / "founders" / founder_slug / "node-usage.json"
    usage_path.parent.mkdir(parents=True, exist_ok=True)

    history = []
    if usage_path.exists():
        try:
            history = json.loads(usage_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            history = []

    history.append(record)
    usage_path.write_text(json.dumps(history, indent=2), encoding="utf-8")

    logger.info("Tracked %d node matches for topic '%s'", len(matched_nodes), topic)

    return {
        "matched_nodes": matched_nodes,
        "record": record,
    }


def load_usage_history(founder_slug: str) -> list[dict]:
    """Load usage history for a founder."""
    usage_path = PROJECT_ROOT / "data" / "founders" / founder_slug / "node-usage.json"
    if not usage_path.exists():
        return []
    try:
        return json.loads(usage_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, Exception):
        return []


def compute_coverage(graph: nx.DiGraph, usage_history: list[dict]) -> dict:
    """Compute coverage statistics — which nodes have been used.

    Returns:
        {
            "overall_pct": float,
            "by_type": {type: {"covered": int, "total": int, "pct": float}},
            "heatmap": {node_id: times_used},
            "opportunities": [{node_id, node_type, label}]
        }
    """
    # Count all usable nodes
    all_nodes = {}
    for nid, data in graph.nodes(data=True):
        ntype = data.get("node_type", "")
        if ntype in ("founder", "category", "vocabulary"):
            continue
        all_nodes[nid] = {
            "node_type": ntype,
            "label": data.get("label", data.get("title", data.get("name", nid))),
        }

    # Count usage from history
    usage_counts = {}
    for record in usage_history:
        for nid in record.get("matched_nodes", []):
            usage_counts[nid] = usage_counts.get(nid, 0) + 1

    # Coverage by type
    by_type = {}
    for nid, info in all_nodes.items():
        ntype = info["node_type"]
        if ntype not in by_type:
            by_type[ntype] = {"covered": 0, "total": 0}
        by_type[ntype]["total"] += 1
        if nid in usage_counts:
            by_type[ntype]["covered"] += 1

    for t in by_type.values():
        t["pct"] = round(t["covered"] / t["total"] * 100, 1) if t["total"] > 0 else 0

    total_nodes = len(all_nodes)
    covered_nodes = sum(1 for nid in all_nodes if nid in usage_counts)
    overall_pct = round(covered_nodes / total_nodes * 100, 1) if total_nodes > 0 else 0

    # Opportunities: unused nodes
    opportunities = [
        {"node_id": nid, "node_type": info["node_type"], "label": info["label"]}
        for nid, info in all_nodes.items()
        if nid not in usage_counts
    ]

    return {
        "overall_pct": overall_pct,
        "total_nodes": total_nodes,
        "covered_nodes": covered_nodes,
        "by_type": by_type,
        "heatmap": usage_counts,
        "opportunities": opportunities,
    }
