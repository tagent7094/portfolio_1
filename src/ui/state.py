"""Streamlit session state management."""

from __future__ import annotations

from pathlib import Path

import streamlit as st
import yaml

PROJECT_ROOT = Path(__file__).parent.parent.parent


def get_config() -> dict:
    """Load LLM config from YAML."""
    config_path = PROJECT_ROOT / "config" / "llm-config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def save_config(config: dict):
    """Save LLM config to YAML."""
    config_path = PROJECT_ROOT / "config" / "llm-config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)


def get_graph():
    """Load the knowledge graph (cached in session state)."""
    from ..graph.store import load_graph

    config = get_config()
    graph_path = PROJECT_ROOT / config["stores"]["graph_path"]
    return load_graph(str(graph_path))


def save_graph_state(graph):
    """Save the graph back to disk."""
    from ..graph.store import save_graph

    config = get_config()
    graph_path = PROJECT_ROOT / config["stores"]["graph_path"]
    save_graph(graph, str(graph_path))


def get_graph_path() -> str:
    """Get the graph file path."""
    config = get_config()
    return str(PROJECT_ROOT / config["stores"]["graph_path"])


def get_personality_card() -> str:
    """Load the personality card text."""
    config = get_config()
    card_path = PROJECT_ROOT / config["stores"]["personality_card_path"]
    if card_path.exists():
        return card_path.read_text(encoding="utf-8")
    return ""


def get_quality_rules() -> dict:
    """Load quality rules config."""
    config_path = PROJECT_ROOT / "config" / "quality-rules.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


COLOR_MAP = {
    "belief": "#378ADD",
    "story": "#1D9E75",
    "style_rule": "#D85A30",
    "thinking_model": "#7F77DD",
    "contrast_pair": "#D4537E",
    "vocabulary": "#888780",
    "unknown": "#888888",
}
