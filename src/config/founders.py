"""Multi-founder config resolution."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "llm-config.yaml"


def _load_config(config_path: str | Path | None = None) -> dict:
    path = Path(config_path) if config_path else CONFIG_PATH
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _save_config(config: dict, config_path: str | Path | None = None):
    path = Path(config_path) if config_path else CONFIG_PATH
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def get_active_founder(config: dict | None = None) -> dict:
    """Return resolved paths for the active founder."""
    if config is None:
        config = _load_config()
    founders = config.get("founders", {})
    active_slug = founders.get("active", "sharath")
    return get_founder_paths(config, active_slug)


def get_founder_paths(config: dict, slug: str) -> dict:
    """Resolve all absolute paths for a founder."""
    founders = config.get("founders", {})
    registry = founders.get("registry", {})
    entry = registry.get(slug)

    if not entry:
        # Fallback to legacy stores section
        stores = config.get("stores", {})
        return {
            "slug": slug,
            "display_name": slug.title(),
            "data_dir": str(PROJECT_ROOT / stores.get("graph_path", "data/founder-data")),
            "graph_path": str(PROJECT_ROOT / stores.get("graph_path", "data/knowledge-graph/graph.json")),
            "personality_card_path": str(PROJECT_ROOT / stores.get("personality_card_path", "data/knowledge-graph/personality-card.md")),
            "vectors_path": str(PROJECT_ROOT / stores.get("vectors_path", "data/knowledge-graph/chroma")),
        }

    return {
        "slug": slug,
        "display_name": entry.get("display_name", slug.title()),
        "data_dir": str(PROJECT_ROOT / entry["data_dir"]),
        "graph_path": str(PROJECT_ROOT / entry["graph_path"]),
        "personality_card_path": str(PROJECT_ROOT / entry["personality_card_path"]),
        "vectors_path": str(PROJECT_ROOT / entry["vectors_path"]),
    }


def list_founders(config: dict | None = None) -> list[dict]:
    """Return list of all registered founders."""
    if config is None:
        config = _load_config()
    founders = config.get("founders", {})
    active = founders.get("active", "")
    registry = founders.get("registry", {})

    result = []
    for slug, entry in registry.items():
        paths = get_founder_paths(config, slug)
        graph_path = Path(paths["graph_path"])
        result.append({
            "slug": slug,
            "display_name": entry.get("display_name", slug.title()),
            "active": slug == active,
            "has_graph": graph_path.exists(),
        })
    return result


def set_active_founder(slug: str, config_path: str | Path | None = None):
    """Switch the active founder in config."""
    config = _load_config(config_path)
    registry = config.get("founders", {}).get("registry", {})
    if slug not in registry:
        raise ValueError(f"Founder '{slug}' not found in registry")
    config["founders"]["active"] = slug
    # Also update legacy stores section
    entry = registry[slug]
    config["stores"] = {
        "graph": "networkx",
        "graph_path": entry["graph_path"],
        "personality_card_path": entry["personality_card_path"],
        "vectors": "chromadb",
        "vectors_path": entry["vectors_path"],
    }
    _save_config(config, config_path)
    logger.info("Active founder set to: %s", slug)


def register_founder(slug: str, display_name: str, config_path: str | Path | None = None) -> dict:
    """Register a new founder with default paths."""
    config = _load_config(config_path)
    if "founders" not in config:
        config["founders"] = {"active": slug, "registry": {}}
    if "registry" not in config["founders"]:
        config["founders"]["registry"] = {}

    base = f"data/founders/{slug}"
    entry = {
        "display_name": display_name,
        "data_dir": f"{base}/founder-data",
        "graph_path": f"{base}/knowledge-graph/graph.json",
        "personality_card_path": f"{base}/knowledge-graph/personality-card.md",
        "vectors_path": f"{base}/knowledge-graph/chroma",
    }
    config["founders"]["registry"][slug] = entry

    # Create directories
    for d in ["founder-data", "knowledge-graph"]:
        (PROJECT_ROOT / base / d).mkdir(parents=True, exist_ok=True)

    _save_config(config, config_path)
    return {"slug": slug, **entry}


def get_viral_graph_path(config: dict | None = None) -> str:
    """Return absolute path to viral graph."""
    if config is None:
        config = _load_config()
    vg = config.get("viral_graph", {})
    return str(PROJECT_ROOT / vg.get("graph_path", "data/viral-graph/graph.json"))


def get_viral_csv_path(config: dict | None = None) -> str:
    """Return absolute path to viral posts CSV."""
    if config is None:
        config = _load_config()
    vg = config.get("viral_graph", {})
    return str(PROJECT_ROOT / vg.get("source_csv", "data/viral-posts-samples/viral-linkedin-posts.csv"))
