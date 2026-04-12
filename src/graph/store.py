"""Save and load the knowledge graph.

Changes from original:
- Issue #28: Fixed double-key edge compatibility to handle all cases
- Added backup before overwrite
- Added validation on load
"""

from __future__ import annotations

import json
import logging
import shutil
import sys
from pathlib import Path

import networkx as nx

logger = logging.getLogger(__name__)


def save_graph(graph: nx.DiGraph, path: str):
    """Save graph to JSON with all node attributes.

    Creates a .bak backup of any existing file before overwriting.
    """
    _log(f"save_graph({path!r}) — {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    # Backup existing file
    if p.exists():
        bak = p.with_suffix(p.suffix + ".bak")
        try:
            shutil.copy2(p, bak)
        except Exception as e:
            _log(f"Warning: backup failed: {e}")

    data = nx.node_link_data(graph)

    # Ensure both 'edges' and 'links' keys exist for cross-version compat
    if "edges" in data and "links" not in data:
        data["links"] = data["edges"]
    elif "links" in data and "edges" not in data:
        data["edges"] = data["links"]

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str, ensure_ascii=False)

    _log(f"→ Saved successfully")
    logger.info("Graph saved to %s (%d nodes, %d edges)", path, graph.number_of_nodes(), graph.number_of_edges())


def load_graph(path: str) -> nx.DiGraph:
    """Load graph from JSON with cross-version NetworkX compatibility."""
    _log(f"load_graph({path!r})")

    p = Path(path)
    if not p.exists() or p.stat().st_size == 0:
        _log("-> No existing graph (missing or empty file), creating empty")
        return nx.DiGraph()

    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            _log(f"-> Corrupt graph JSON ({e}), creating empty")
            return nx.DiGraph()

    # Ensure both keys exist regardless of which NetworkX version saved it
    edges = data.get("edges", data.get("links", []))
    data["edges"] = edges
    data["links"] = edges

    try:
        graph = nx.node_link_graph(data, edges="edges")
    except TypeError:
        try:
            graph = nx.node_link_graph(data)
        except Exception as e:
            _log(f"Warning: node_link_graph failed, trying manual build: {e}")
            graph = _manual_load(data)

    # Normalize edge keys: ensure all edges use 'edge_type' (some graphs use 'type')
    for u, v, data in graph.edges(data=True):
        if "edge_type" not in data and "type" in data:
            data["edge_type"] = data.pop("type")

    # Validate
    n_nodes = graph.number_of_nodes()
    n_edges = graph.number_of_edges()
    _log(f"→ Loaded {n_nodes} nodes, {n_edges} edges")

    if n_nodes == 0:
        _log("Warning: loaded graph has 0 nodes")

    return graph


def _manual_load(data: dict) -> nx.DiGraph:
    """Manual graph construction as fallback."""
    graph = nx.DiGraph()

    # Graph-level attributes
    for key, val in data.get("graph", {}).items():
        graph.graph[key] = val

    # Nodes
    for node in data.get("nodes", []):
        nid = node.get("id", node.get("key", ""))
        if not nid:
            continue
        attrs = {k: v for k, v in node.items() if k not in ("id", "key")}
        graph.add_node(nid, **attrs)

    # Edges
    for edge in data.get("edges", data.get("links", [])):
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if src and tgt:
            attrs = {k: v for k, v in edge.items() if k not in ("source", "target")}
            graph.add_edge(src, tgt, **attrs)

    return graph


def _log(msg: str):
    print(f"\033[33m[GraphStore]\033[0m {msg}", file=sys.stderr, flush=True)