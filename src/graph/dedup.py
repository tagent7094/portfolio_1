"""Deduplicate knowledge graph nodes by semantic similarity.

Changes from original:
- Added fallback dedup using difflib when no embedder is available
- Tightened thresholds for style rules (0.75) to catch paraphrased duplicates (Issue #13)
- deduplicate_graph() now also merges metadata from removed nodes
- Added dedup stats logging
"""

from __future__ import annotations

import re
import sys
import logging
from collections import defaultdict
from difflib import SequenceMatcher

import networkx as nx

logger = logging.getLogger(__name__)


def _text_similarity(a: str, b: str) -> float:
    """Fallback similarity using max of character-level and token-level Jaccard.

    Character-level (SequenceMatcher) catches near-exact duplicates.
    Token Jaccard catches paraphrases that use the same key words in different order.
    """
    if not a or not b:
        return 0.0

    a_lower = a.lower().strip()
    b_lower = b.lower().strip()

    # Character-level
    char_sim = SequenceMatcher(None, a_lower, b_lower).ratio()

    # Token-level Jaccard (ignores word order, catches paraphrases)
    tokens_a = set(re.findall(r"[a-z]{3,}", a_lower))
    tokens_b = set(re.findall(r"[a-z]{3,}", b_lower))
    if tokens_a and tokens_b:
        intersection = len(tokens_a & tokens_b)
        union = len(tokens_a | tokens_b)
        token_sim = intersection / union if union else 0.0
    else:
        token_sim = 0.0

    return max(char_sim, token_sim)


def _compute_similarity(text_a: str, text_b: str, embedder=None) -> float:
    """Compute similarity using embedder if available, else fallback."""
    if embedder is not None:
        try:
            return embedder.similarity(text_a, text_b)
        except Exception:
            pass
    return _text_similarity(text_a, text_b)


def _dedup_list(
    items: list[dict],
    field: str,
    embedder=None,
    threshold: float = 0.85,
) -> list[dict]:
    """Deduplicate a list of dicts by semantic similarity on a specific text field."""
    if len(items) <= 1:
        return items

    unique = [items[0]]
    skipped = 0

    for item in items[1:]:
        text = item.get(field, "")
        if not text:
            unique.append(item)
            continue

        is_dup = False
        for i, existing in enumerate(unique):
            existing_text = existing.get(field, "")
            if not existing_text:
                continue

            sim = _compute_similarity(text, existing_text, embedder)
            if sim > threshold:
                # Keep the one with more content
                if len(text) > len(existing_text):
                    unique[i] = item
                is_dup = True
                skipped += 1
                break

        if not is_dup:
            unique.append(item)

    if skipped > 0:
        _log(f"Pre-build dedup [{field}]: {len(items)} → {len(unique)} ({skipped} removed)")

    return unique


def dedup_extracted_data(extracted_data: dict, embedder=None) -> dict:
    """Deduplicate all node types in extracted data before graph building."""
    _log("Starting pre-build deduplication...")

    result = {**extracted_data}

    result["beliefs"] = _dedup_list(result.get("beliefs", []), "stance", embedder, threshold=0.78)
    result["stories"] = _dedup_list(result.get("stories", []), "summary", embedder, threshold=0.75)
    result["style_rules"] = _dedup_list(result.get("style_rules", []), "description", embedder, threshold=0.72)
    result["thinking_models"] = _dedup_list(result.get("thinking_models", []), "description", embedder, threshold=0.78)

    _log(f"Pre-build dedup done: {len(result['beliefs'])}B, {len(result['stories'])}S, "
         f"{len(result['style_rules'])}R, {len(result['thinking_models'])}M")

    return result


def deduplicate_graph(graph: nx.DiGraph, embedder=None) -> tuple[nx.DiGraph, dict]:
    """Deduplicate an existing graph by removing semantically similar nodes.

    Now also works without an embedder (uses difflib fallback).
    Merges metadata (evidence_quotes, key_quotes) from removed nodes into kept nodes.
    """
    _log(f"Post-build dedup: {graph.number_of_nodes()} nodes...")

    by_type: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for nid, data in graph.nodes(data=True):
        ntype = data.get("node_type", "")
        if ntype not in ("founder", "category", "vocabulary"):
            by_type[ntype].append((nid, data))

    type_fields = {
        "belief": ("stance", 0.78),
        "story": ("summary", 0.75),
        "style_rule": ("description", 0.42),  # Low threshold: many paraphrased duplicates
        "thinking_model": ("description", 0.65),
        "contrast_pair": ("description", 0.70),
    }

    total_removed = 0
    stats = {}

    for ntype, nodes in by_type.items():
        field_info = type_fields.get(ntype)
        if not field_info or len(nodes) <= 1:
            continue

        field, threshold = field_info
        keep_ids = set()
        remove_ids = set()
        merge_map: dict[str, str] = {}  # removed_id → kept_id

        for i, (nid_a, data_a) in enumerate(nodes):
            if nid_a in remove_ids:
                continue
            text_a = data_a.get(field, "")
            if not text_a:
                keep_ids.add(nid_a)
                continue

            keep_ids.add(nid_a)

            for j in range(i + 1, len(nodes)):
                nid_b, data_b = nodes[j]
                if nid_b in remove_ids:
                    continue
                text_b = data_b.get(field, "")
                if not text_b:
                    continue

                sim = _compute_similarity(text_a, text_b, embedder)
                if sim > threshold:
                    remove_ids.add(nid_b)
                    merge_map[nid_b] = nid_a

                    # Merge metadata from B into A
                    _merge_node_metadata(graph, nid_a, nid_b)

                    # Redirect edges
                    for pred in list(graph.predecessors(nid_b)):
                        edge_data = graph.edges[pred, nid_b]
                        if not graph.has_edge(pred, nid_a) and pred != nid_a:
                            graph.add_edge(pred, nid_a, **edge_data)

                    for succ in list(graph.successors(nid_b)):
                        edge_data = graph.edges[nid_b, succ]
                        if not graph.has_edge(nid_a, succ) and succ != nid_a:
                            graph.add_edge(nid_a, succ, **edge_data)

        for nid in remove_ids:
            graph.remove_node(nid)

        if remove_ids:
            _log(f"  {ntype}: removed {len(remove_ids)} duplicates (kept {len(keep_ids)})")
            stats[ntype] = {"removed": len(remove_ids), "kept": len(keep_ids)}
            total_removed += len(remove_ids)

    _log(f"Post-build dedup done: removed {total_removed}, {graph.number_of_nodes()} remaining")

    return graph, {"total_removed": total_removed, "by_type": stats, "merge_map": {}}


def _merge_node_metadata(graph: nx.DiGraph, keep_id: str, remove_id: str):
    """Merge useful metadata from the removed node into the kept node."""
    keep = graph.nodes[keep_id]
    remove = graph.nodes[remove_id]

    # Merge list fields
    for list_field in ("evidence_quotes", "key_quotes", "examples", "source_chunks"):
        keep_list = keep.get(list_field, [])
        remove_list = remove.get(list_field, [])
        if isinstance(keep_list, list) and isinstance(remove_list, list):
            existing = set(str(x).lower() for x in keep_list)
            for item in remove_list:
                if str(item).lower() not in existing:
                    keep_list.append(item)
            keep[list_field] = keep_list

    # Keep higher confidence
    if "confidence" in keep and "confidence" in remove:
        keep["confidence"] = max(keep["confidence"], remove["confidence"])

    # Keep higher engagement
    if "engagement" in keep and "engagement" in remove:
        keep["engagement"] = max(keep.get("engagement", 0), remove.get("engagement", 0))


def _log(msg: str):
    print(f"\033[35m[Dedup]\033[0m {msg}", file=sys.stderr, flush=True)