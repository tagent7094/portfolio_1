"""Tests for the humanization layer."""

import pytest
import networkx as nx

from src.graph.builder import build_graph


def _make_test_graph():
    data = {
        "beliefs": [],
        "stories": [],
        "style_rules": [
            {"id": "no_em_dash", "rule_type": "punctuation", "description": "Never use em dashes", "anti_pattern": "Using em dashes"},
        ],
        "thinking_models": [],
        "vocabulary": {
            "phrases_used": ["the reality is", "here's the thing"],
            "phrases_never": ["leverage", "synergy", "at the end of the day"],
            "pronoun_rules": {"prefer": "we", "avoid": "I"},
        },
    }
    return build_graph(data)


def test_quality_gate_good_post():
    from src.humanization.quality_gate import quality_gate

    graph = _make_test_graph()
    post = (
        "Most founders think AI will replace their support team. They're wrong.\n\n"
        "We built a $12M ARR business by investing in people, not chatbots. "
        "Our retention rate is 94%. Our NPS is 72. But that's not because of technology.\n\n"
        "It's because when a Fortune 500 client calls at 2am on Black Friday, "
        "a human picks up. Not a bot. Not an IVR. A person who knows their business.\n\n"
        "The companies racing to automate everything will learn this lesson the hard way. "
        "Customer trust isn't built in the easy moments. It's built in the hard ones.\n\n"
        "The future of support isn't AI vs humans. It's AI enabling humans to be better."
    )
    result = quality_gate(post, graph)
    assert result["score"] >= 50
    assert isinstance(result["checks"], dict)


def test_quality_gate_bad_post():
    from src.humanization.quality_gate import quality_gate

    graph = _make_test_graph()
    post = "Everyone says AI is the future. What do you think? Let me know in the comments!"
    result = quality_gate(post, graph)
    assert result["checks"]["no_generic_opening"] is False
    assert result["checks"]["no_cta_ending"] is False


def test_quality_gate_banned_phrases():
    from src.humanization.quality_gate import quality_gate

    graph = _make_test_graph()
    post = "We need to leverage synergy to drive growth. At the end of the day, it matters."
    result = quality_gate(post, graph)
    assert result["checks"]["no_banned_phrases"] is False
