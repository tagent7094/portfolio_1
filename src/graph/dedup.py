"""Deduplicate knowledge graph nodes by semantic similarity."""

from __future__ import annotations

import sys
import logging
from collections import defaultdict

import networkx as nx

logger = logging.getLogger(__name__)


def _dedup_list(items: list[dict], field: str, embedder, threshold: float = 0.85) -> list[dict]:
    """Deduplicate a list of dicts by semantic similarity on a specific text field.

    Keeps the first occurrence. If a duplicate has longer content in the field, it replaces the original.
    """
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
        for existing in unique:
            existing_text = existing.get(field, "")
            if not existing_text:
                continue
            sim = embedder.similarity(text, existing_text)
            if sim > threshold:
                # Keep the one with more content
                if len(text) > len(existing_text):
                    unique.remove(existing)
                    unique.append(item)
                is_dup = True
                skipped += 1
                break

        if not is_dup:
            unique.append(item)

    if skipped > 0:
        print(f"\033[35m[Dedup]\033[0m {field}: {len(items)} → {len(unique)} ({skipped} duplicates removed)", file=sys.stderr, flush=True)

    return unique


def dedup_extracted_data(extracted_data: dict, embedder) -> dict:
    """Deduplicate all node types in extracted data before graph building.

    Args:
        extracted_data: dict with keys: beliefs, stories, style_rules, thinking_models
        embedder: Embedder instance for semantic similarity

    Returns:
        Same dict with deduplicated lists
    """
    print(f"\033[35m[Dedup]\033[0m Starting deduplication...", file=sys.stderr, flush=True)

    result = {**extracted_data}

    result["beliefs"] = _dedup_list(result.get("beliefs", []), "stance", embedder, threshold=0.80)
    result["stories"] = _dedup_list(result.get("stories", []), "summary", embedder, threshold=0.78)
    result["style_rules"] = _dedup_list(result.get("style_rules", []), "description", embedder, threshold=0.82)
    result["thinking_models"] = _dedup_list(result.get("thinking_models", []), "description", embedder, threshold=0.82)

    print(f"\033[35m[Dedup]\033[0m \033[32m→ Done: {len(result['beliefs'])} beliefs, {len(result['stories'])} stories, "
          f"{len(result['style_rules'])} rules, {len(result['thinking_models'])} models\033[0m", file=sys.stderr, flush=True)

    return result


def deduplicate_graph(graph: nx.DiGraph, embedder) -> tuple[nx.DiGraph, dict]:
    """Deduplicate an existing graph in-place by removing duplicate nodes.

    Finds nodes with semantically similar content and merges them
    (keeps one, redirects edges, removes the duplicate).

    Returns (cleaned_graph, stats_dict)
    """
    print(f"\033[35m[GraphDedup]\033[0m Deduplicating graph with {graph.number_of_nodes()} nodes...", file=sys.stderr, flush=True)

    # Group nodes by type
    by_type: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for nid, data in graph.nodes(data=True):
        ntype = data.get("node_type", "")
        if ntype not in ("founder", "category", "vocabulary"):
            by_type[ntype].append((nid, data))

    # Field to compare for each type
    type_fields = {
        "belief": ("stance", 0.80),
        "story": ("summary", 0.78),
        "style_rule": ("description", 0.82),
        "thinking_model": ("description", 0.82),
        "contrast_pair": ("description", 0.82),
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

        # O(n²) comparison — fine for <500 nodes per type
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

                sim = embedder.similarity(text_a, text_b)
                if sim > threshold:
                    # Remove B, redirect its edges to A
                    remove_ids.add(nid_b)

                    # Redirect edges
                    for pred in list(graph.predecessors(nid_b)):
                        edge_data = graph.edges[pred, nid_b]
                        if not graph.has_edge(pred, nid_a) and pred != nid_a:
                            graph.add_edge(pred, nid_a, **edge_data)

                    for succ in list(graph.successors(nid_b)):
                        edge_data = graph.edges[nid_b, succ]
                        if not graph.has_edge(nid_a, succ) and succ != nid_a:
                            graph.add_edge(nid_a, succ, **edge_data)

        # Remove duplicates
        for nid in remove_ids:
            graph.remove_node(nid)

        if remove_ids:
            print(f"\033[35m[GraphDedup]\033[0m {ntype}: removed {len(remove_ids)} duplicates (kept {len(keep_ids)})", file=sys.stderr, flush=True)
            stats[ntype] = {"removed": len(remove_ids), "kept": len(keep_ids)}
            total_removed += len(remove_ids)

    print(f"\033[35m[GraphDedup]\033[0m \033[32m→ Total: removed {total_removed} duplicates, "
          f"{graph.number_of_nodes()} nodes remaining\033[0m", file=sys.stderr, flush=True)

    return graph, {"total_removed": total_removed, "by_type": stats}
