"""Load/save admin model defaults and per-founder overrides.

Mirrors the precedent at `src/batch/notify.py:18-32` — JSON files at well-known
paths, atomic writes, graceful failure on missing/corrupt files. Two stores:

  - `config/models-config.json`                        — admin defaults
  - `data/founders/<slug>/config/models-override.json` — per-founder partial overrides
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .task_catalog import TASK_CATALOG, validate_task_id

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent
ADMIN_CONFIG_PATH = PROJECT_ROOT / "config" / "models-config.json"


def _founder_override_path(slug: str) -> Path:
    return PROJECT_ROOT / "data" / "founders" / slug / "config" / "models-override.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _empty_admin_config() -> dict:
    """Build a default admin config from the task catalog.

    Tasks tagged `default_purpose=generation` map to claude-opus-4-6, `prep` to
    claude-haiku-4-5-20251001, `ingestion` to nvidia/nemotron. Operators can
    overwrite any task via the admin UI.
    """
    purpose_defaults = {
        "generation": {"provider": "anthropic", "model": "claude-opus-4-6", "enable_thinking": True, "effort": "high"},
        "prep":       {"provider": "anthropic", "model": "claude-haiku-4-5-20251001", "enable_thinking": False, "effort": "low"},
        "ingestion":  {"provider": "nvidia",    "model": "nvidia/nemotron-3-super-120b-a12b"},
    }
    tasks = {}
    for task_id, spec in TASK_CATALOG.items():
        base = purpose_defaults.get(spec.default_purpose, purpose_defaults["generation"]).copy()
        base["max_tokens"] = spec.default_max_tokens
        base["temperature"] = spec.default_temperature
        tasks[task_id] = base
    return {
        "version": 1,
        "updated_at": _now_iso(),
        "tasks": tasks,
    }


def load_admin_config() -> dict:
    """Return admin defaults; falls back to a synthesised default when missing.

    Returning a populated dict (instead of empty) means the LLMRouter always
    has *something* to resolve against — first run on a fresh deploy works.
    The returned dict carries `_synthesized: True` when the on-disk file is
    absent, so the router can label resolution source as `default` (not `admin`).
    """
    if ADMIN_CONFIG_PATH.exists():
        try:
            cfg = json.loads(ADMIN_CONFIG_PATH.read_text(encoding="utf-8"))
            cfg["_synthesized"] = False
            return cfg
        except Exception as e:
            logger.warning("[models_config] admin config corrupt (%s) — using synthesised defaults", e)
    cfg = _empty_admin_config()
    cfg["_synthesized"] = True
    return cfg


def save_admin_config(cfg: dict) -> dict:
    """Validate + persist. Unknown task_ids and missing required fields are rejected."""
    if not isinstance(cfg, dict) or "tasks" not in cfg:
        raise ValueError("admin config must be a dict with a 'tasks' field")
    for task_id, task_cfg in cfg["tasks"].items():
        if not validate_task_id(task_id):
            raise ValueError(f"unknown task_id: {task_id!r}")
        if not isinstance(task_cfg, dict):
            raise ValueError(f"task config for {task_id!r} must be a dict")
        if "provider" not in task_cfg or "model" not in task_cfg:
            raise ValueError(f"task {task_id!r} missing required 'provider' or 'model'")
    cfg["updated_at"] = _now_iso()
    cfg.setdefault("version", 1)
    ADMIN_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = ADMIN_CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    tmp.replace(ADMIN_CONFIG_PATH)
    logger.info("[models_config] admin config saved (%d tasks)", len(cfg["tasks"]))
    return cfg


def load_founder_override(slug: str) -> dict:
    """Return the founder's partial override dict, or an empty skeleton."""
    p = _founder_override_path(slug)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("[models_config] founder override corrupt for %s (%s) — treating as empty", slug, e)
    return {"version": 1, "updated_at": "", "tasks": {}}


def save_founder_override(slug: str, cfg: dict) -> dict:
    """Validate + persist a founder override. Only task entries are kept."""
    if not isinstance(cfg, dict):
        raise ValueError("founder override must be a dict")
    tasks_in = cfg.get("tasks") or {}
    cleaned: dict[str, dict] = {}
    for task_id, task_cfg in tasks_in.items():
        if not validate_task_id(task_id):
            raise ValueError(f"unknown task_id: {task_id!r}")
        if not isinstance(task_cfg, dict):
            raise ValueError(f"override for {task_id!r} must be a dict")
        if "provider" not in task_cfg or "model" not in task_cfg:
            raise ValueError(f"override for {task_id!r} missing required 'provider' or 'model'")
        cleaned[task_id] = task_cfg
    out = {"version": 1, "updated_at": _now_iso(), "tasks": cleaned}
    p = _founder_override_path(slug)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(out, indent=2), encoding="utf-8")
    tmp.replace(p)
    logger.info("[models_config] founder override saved for %s (%d tasks)", slug, len(cleaned))
    return out


def delete_founder_override_task(slug: str, task_id: str) -> dict:
    """Remove a single task override and persist. Returns the updated override dict."""
    current = load_founder_override(slug)
    tasks = current.get("tasks") or {}
    if task_id in tasks:
        del tasks[task_id]
    current["tasks"] = tasks
    return save_founder_override(slug, current)


def merged_config_for_founder(slug: str | None) -> dict:
    """Return the full resolved config + source labels for the UI.

    Output: `{admin_defaults, founder_overrides, resolved}` where each task in
    `resolved` carries a `_source` key indicating where the resolved values
    came from. The frontend uses this for the "founder / admin / default" badge.
    """
    admin = load_admin_config()
    admin_synthesized = bool(admin.get("_synthesized"))
    founder = load_founder_override(slug) if slug else {"tasks": {}}
    resolved: dict[str, dict] = {}
    admin_tasks = admin.get("tasks") or {}
    founder_tasks = founder.get("tasks") or {}
    for task_id, spec in TASK_CATALOG.items():
        if task_id in founder_tasks:
            entry = {**founder_tasks[task_id], "_source": "founder"}
        elif task_id in admin_tasks:
            entry = {**admin_tasks[task_id], "_source": "default" if admin_synthesized else "admin"}
        else:
            entry = {
                "provider": "anthropic",
                "model": "claude-opus-4-6" if spec.default_purpose == "generation" else "claude-haiku-4-5-20251001",
                "max_tokens": spec.default_max_tokens,
                "temperature": spec.default_temperature,
                "_source": "default",
            }
        resolved[task_id] = entry
    return {
        "admin_defaults": admin,
        "founder_overrides": founder,
        "resolved": resolved,
    }
