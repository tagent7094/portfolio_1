"""Save and load the knowledge graph."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import networkx as nx

logger = logging.getLogger(__name__)


def save_graph(graph: nx.DiGraph, path: str):
    """Save graph to JSON with all node attributes."""
    print(f"\033[33m[GraphStore]\033[0m save_graph(path={path!r}) — {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges", file=sys.stderr, flush=True)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    data = nx.node_link_data(graph)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"\033[33m[GraphStore]\033[0m \033[32m→ Graph saved successfully\033[0m", file=sys.stderr, flush=True)
    logger.info("Graph saved to %s (%d nodes, %d edges)", path, graph.number_of_nodes(), graph.number_of_edges())


def load_graph(path: str) -> nx.DiGraph:
    """Load graph from JSON."""
    print(f"\033[33m[GraphStore]\033[0m load_graph(path={path!r})", file=sys.stderr, flush=True)
    if not Path(path).exists():
        print(f"\033[33m[GraphStore]\033[0m → No existing graph, creating empty", file=sys.stderr, flush=True)
        logger.info("No existing graph at %s, creating empty graph", path)
        return nx.DiGraph()
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Handle both 'edges' and 'links' keys across NetworkX versions
    # NetworkX <3.4 expects 'links'; NetworkX >=3.4 expects 'edges'
    if "links" in data and "edges" not in data:
        data["edges"] = data["links"]
    elif "edges" in data and "links" not in data:
        data["links"] = data["edges"]
    # Try with edges= parameter first (NX 3.4+), fall back to links
    try:
        graph = nx.node_link_graph(data, edges="edges")
    except TypeError:
        graph = nx.node_link_graph(data)
    print(f"\033[33m[GraphStore]\033[0m \033[32m→ Loaded {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges\033[0m", file=sys.stderr, flush=True)
    logger.info("Graph loaded from %s (%d nodes, %d edges)", path, graph.number_of_nodes(), graph.number_of_edges())
    return graph
