"""LangChain tools for querying the knowledge graph and vector store."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool


@tool
def query_graph_beliefs(topic: str) -> str:
    """Query the knowledge graph for beliefs related to a topic. Returns beliefs sorted by confidence."""
    from ..graph.store import load_graph
    from ..graph.query import get_beliefs_for_topic

    graph = _get_graph()
    beliefs = get_beliefs_for_topic(graph, topic)
    return json.dumps(beliefs[:10], default=str)


@tool
def query_graph_stories(topic: str) -> str:
    """Query the knowledge graph for stories related to a topic."""
    from ..graph.store import load_graph
    from ..graph.query import get_beliefs_for_topic, get_stories_for_beliefs

    graph = _get_graph()
    beliefs = get_beliefs_for_topic(graph, topic)
    belief_ids = [b.get("id", "") for b in beliefs]
    stories = get_stories_for_beliefs(graph, belief_ids)
    return json.dumps(stories[:10], default=str)


@tool
def query_style_rules(platform: str) -> str:
    """Get writing style rules for a specific platform (linkedin, twitter, email)."""
    from ..graph.query import get_style_rules_for_platform

    graph = _get_graph()
    rules = get_style_rules_for_platform(graph, platform)
    return json.dumps(rules[:15], default=str)


@tool
def query_vocabulary() -> str:
    """Get vocabulary rules: phrases to use, phrases to never use, pronoun rules."""
    from ..graph.query import get_vocabulary_rules

    graph = _get_graph()
    return json.dumps(get_vocabulary_rules(graph), default=str)


@tool
def get_personality_card_tool() -> str:
    """Get the founder's personality card — a natural language summary of their identity and voice."""
    from ..graph.query import get_personality_card

    graph = _get_graph()
    return get_personality_card(graph)


@tool
def search_similar_content(query: str) -> str:
    """Search the vector store for content similar to the query text."""
    try:
        from ..vectors.embedder import Embedder
        from ..vectors.store import VectorStore
        from pathlib import Path

        project_root = Path(__file__).parent.parent.parent
        vs = VectorStore(persist_dir=str(project_root / "data" / "knowledge-graph" / "chroma"))
        embedder = Embedder()
        query_emb = embedder.embed([query])[0]
        results = vs.search(query_embedding=query_emb, n_results=5)
        if results and results.get("documents"):
            return json.dumps(results["documents"][0][:3])
        return "No similar content found."
    except Exception:
        return "Vector store not available."


@tool
def check_quality_gate(post: str) -> str:
    """Run the quality gate on a generated post. Returns score and individual check results."""
    from ..humanization.quality_gate import quality_gate

    graph = _get_graph()
    result = quality_gate(post, graph)
    return json.dumps(result, default=str)


def _get_graph():
    """Load the knowledge graph (cached in module)."""
    from ..graph.store import load_graph
    from pathlib import Path

    project_root = Path(__file__).parent.parent.parent
    graph_path = project_root / "data" / "knowledge-graph" / "graph.json"
    return load_graph(str(graph_path))
