"""Tests for the knowledge graph module."""

import tempfile
from pathlib import Path

import pytest


def test_build_graph_from_extracted_data():
    from src.graph.builder import build_graph

    data = {
        "beliefs": [
            {"id": "ai_augment", "topic": "ai_automation", "stance": "AI augments not replaces", "confidence": 0.9},
            {"id": "hire_attitude", "topic": "hiring", "stance": "Hire for attitude over aptitude", "confidence": 0.95},
        ],
        "stories": [
            {
                "id": "black_friday",
                "title": "Black Friday 2am call",
                "summary": "Stayed 6 hours on phone with Fortune 500 client",
                "emotional_register": "quiet_authority",
                "best_used_for": ["ai_automation", "customer_trust"],
            }
        ],
        "style_rules": [
            {"id": "short_paras", "rule_type": "rhythm", "description": "Short punchy paragraphs, max 3 sentences"},
        ],
        "thinking_models": [
            {"id": "narrative_vs_reality", "name": "narrative_vs_reality", "description": "Separates hype from reality", "priority": 9},
        ],
        "personality_card": "Test personality card",
    }

    graph = build_graph(data)
    assert graph.number_of_nodes() >= 4
    assert graph.graph.get("personality_card") == "Test personality card"


def test_save_load_graph():
    from src.graph.builder import build_graph
    from src.graph.store import save_graph, load_graph

    data = {
        "beliefs": [{"id": "test", "topic": "test", "stance": "Test belief", "confidence": 0.8}],
        "stories": [],
        "style_rules": [],
        "thinking_models": [],
    }

    graph = build_graph(data)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name

    try:
        save_graph(graph, path)
        loaded = load_graph(path)
        assert loaded.number_of_nodes() == graph.number_of_nodes()
    finally:
        Path(path).unlink(missing_ok=True)


def test_query_beliefs_for_topic():
    from src.graph.builder import build_graph
    from src.graph.query import get_beliefs_for_topic

    data = {
        "beliefs": [
            {"id": "ai_1", "topic": "ai_automation", "stance": "AI augments", "confidence": 0.9},
            {"id": "hire_1", "topic": "hiring", "stance": "Hire for attitude", "confidence": 0.8},
        ],
        "stories": [],
        "style_rules": [],
        "thinking_models": [],
    }

    graph = build_graph(data)
    beliefs = get_beliefs_for_topic(graph, "ai_automation")
    assert len(beliefs) >= 1
    assert beliefs[0]["confidence"] == 0.9


def test_get_vocabulary_rules_empty():
    from src.graph.query import get_vocabulary_rules
    import networkx as nx

    graph = nx.DiGraph()
    vocab = get_vocabulary_rules(graph)
    assert vocab == {"phrases_used": [], "phrases_never": [], "pronoun_rules": {}}
