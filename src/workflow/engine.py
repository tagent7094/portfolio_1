"""Workflow engine — dynamically builds LangGraph from visual workflow config."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .registry import DEFAULT_WORKFLOW, WORKFLOW_NODE_TYPES

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent
WORKFLOWS_DIR = PROJECT_ROOT / "data" / "workflows"


def load_workflow(workflow_id: str = "default") -> dict:
    """Load a workflow config from disk, or return default."""
    path = WORKFLOWS_DIR / f"{workflow_id}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return DEFAULT_WORKFLOW.copy()


def save_workflow(config: dict) -> str:
    """Save a workflow config to disk."""
    WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
    wid = config.get("id", "default")
    path = WORKFLOWS_DIR / f"{wid}.json"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    logger.info("Workflow saved: %s", path)
    return str(path)


def list_workflows() -> list[dict]:
    """List all saved workflows."""
    WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
    result = []
    for f in WORKFLOWS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            result.append({"id": data.get("id", f.stem), "name": data.get("name", f.stem)})
        except Exception:
            pass
    if not result:
        result.append({"id": "default", "name": "Default Pipeline"})
    return result


def get_node_types() -> list[dict]:
    """Return all available node types for the UI."""
    return [
        {"id": nid, **info}
        for nid, info in WORKFLOW_NODE_TYPES.items()
    ]
